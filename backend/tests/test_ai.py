"""AI provider layer: the shared client (validation retry, typed errors, ai_requests
logging, daily limit), the provider factory, and the OpenAI-compatible adapter against
an httpx2 MockTransport. No real LLM calls are made."""

import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIClient, AIClientDep
from app.ai.errors import AIDailyLimitError, AIDisabledError, AIOutputError, AIProviderError
from app.ai.providers.base import ProviderCallError, ProviderOutputError, Usage
from app.ai.providers.factory import AIConfigError, build_provider
from app.ai.providers.openai_compat import OpenAICompatibleProvider
from app.core.config import Settings, get_settings
from app.core.dependencies import CurrentUser
from app.db.base import utcnow
from app.main import create_app
from app.models import User
from app.models.ai import AIRequest
from app.models.enums import AIFeature
from tests.ai_fakes import FakeProvider
from tests.auth_helpers import use_new_session
from tests.conftest import settings_with
from tests.factories import make_user

pytestmark = pytest.mark.anyio


class Draft(BaseModel):
    title: str
    hours: float | None = Field(gt=0, le=24)


GOOD = Draft(title="Fixed login", hours=2.5)


def _client(db: AsyncSession, provider: Any, **settings: Any) -> AIClient:
    return AIClient(provider, db, settings_with(**settings))


async def _structured(ai: AIClient, user: User) -> Draft:
    return await ai.generate_structured(
        user, AIFeature.NL_LOG_ENTRY, system="sys", prompt="text", schema=Draft
    )


async def _rows(db: AsyncSession, user: User) -> list[AIRequest]:
    result = await db.scalars(
        select(AIRequest).where(AIRequest.user_id == user.id).order_by(AIRequest.id)
    )
    return list(result)


# --- Client: validation, retry, typed errors, logging -------------------------------


async def test_structured_success_writes_one_row(db: AsyncSession) -> None:
    user = await make_user(db)
    fake = FakeProvider(GOOD, usage=Usage(input_tokens=120, output_tokens=30))

    assert await _structured(_client(db, fake), user) == GOOD

    rows = await _rows(db, user)
    assert [(r.success, r.input_tokens, r.output_tokens) for r in rows] == [(True, 120, 30)]
    assert (rows[0].feature, rows[0].provider, rows[0].model) == (
        AIFeature.NL_LOG_ENTRY,
        "fake",
        "fake-model",
    )
    assert fake.calls[0]["schema"] is Draft


async def test_validation_failure_is_retried_once(db: AsyncSession) -> None:
    user = await make_user(db)
    fake = FakeProvider(ProviderOutputError("bad json", Usage(50, 10)), GOOD)

    assert await _structured(_client(db, fake), user) == GOOD

    rows = await _rows(db, user)
    assert [(r.success, r.input_tokens) for r in rows] == [(False, 50), (True, 100)]
    assert len(fake.calls) == 2


async def test_second_validation_failure_raises_typed_error(db: AsyncSession) -> None:
    user = await make_user(db)
    fake = FakeProvider(ProviderOutputError("bad"), ProviderOutputError("still bad"))

    with pytest.raises(AIOutputError) as exc:
        await _structured(_client(db, fake), user)

    assert (exc.value.status_code, exc.value.code) == (502, "ai_invalid_output")
    assert [r.success for r in await _rows(db, user)] == [False, False]


async def test_wrong_output_type_counts_as_validation_failure(db: AsyncSession) -> None:
    user = await make_user(db)
    fake = FakeProvider({"title": "not a model"}, GOOD)

    assert await _structured(_client(db, fake), user) == GOOD
    assert [r.success for r in await _rows(db, user)] == [False, True]


async def test_provider_call_error_is_not_retried(db: AsyncSession) -> None:
    user = await make_user(db)
    fake = FakeProvider(ProviderCallError("RateLimitError (HTTP 429)"), GOOD)

    with pytest.raises(AIProviderError) as exc:
        await _structured(_client(db, fake), user)

    assert (exc.value.status_code, exc.value.code) == (502, "ai_provider_error")
    assert len(fake.calls) == 1
    rows = await _rows(db, user)
    assert [(r.success, r.input_tokens, r.output_tokens) for r in rows] == [(False, 0, 0)]


async def test_unexpected_error_still_writes_row(db: AsyncSession) -> None:
    user = await make_user(db)
    fake = FakeProvider(RuntimeError("adapter bug"))

    with pytest.raises(RuntimeError):
        await _structured(_client(db, fake), user)

    assert [r.success for r in await _rows(db, user)] == [False]


async def test_text_call_writes_row(db: AsyncSession) -> None:
    user = await make_user(db)
    fake = FakeProvider("The team logged 40 hours.")

    text = await _client(db, fake).generate_text(
        user, AIFeature.TEAM_SUMMARY, system="sys", prompt="numbers"
    )

    assert text == "The team logged 40 hours."
    rows = await _rows(db, user)
    assert [(r.feature, r.success) for r in rows] == [(AIFeature.TEAM_SUMMARY, True)]


async def test_text_output_error_raises_typed_error(db: AsyncSession) -> None:
    user = await make_user(db)
    fake = FakeProvider(ProviderOutputError("empty"))

    with pytest.raises(AIOutputError):
        await _client(db, fake).generate_text(user, AIFeature.TEAM_SUMMARY, system="s", prompt="p")
    assert [r.success for r in await _rows(db, user)] == [False]


async def test_disabled_when_no_provider(db: AsyncSession) -> None:
    user = await make_user(db)
    with pytest.raises(AIDisabledError):
        await _structured(_client(db, None), user)
    assert await _rows(db, user) == []


# --- Daily limit ------------------------------------------------------------------


async def _add_rows(db: AsyncSession, user: User, n: int, *, days_ago: int = 0) -> None:
    for _ in range(n):
        db.add(
            AIRequest(
                user_id=user.id,
                feature=AIFeature.DAILY_PLAN,
                provider="fake",
                model="fake-model",
                success=True,
                created_at=utcnow() - timedelta(days=days_ago),
            )
        )
    await db.flush()


async def test_daily_limit_blocks_before_calling_provider(db: AsyncSession) -> None:
    user = await make_user(db)
    await _add_rows(db, user, 2)
    fake = FakeProvider(GOOD)

    with pytest.raises(AIDailyLimitError) as exc:
        await _structured(_client(db, fake, ai_daily_limit_per_user=2), user)

    assert (exc.value.status_code, exc.value.code) == (429, "ai_daily_limit_exceeded")
    assert fake.calls == []
    assert len(await _rows(db, user)) == 2


async def test_daily_limit_counts_only_today_and_own_rows(db: AsyncSession) -> None:
    user = await make_user(db)
    other = await make_user(db)
    await _add_rows(db, user, 5, days_ago=2)
    await _add_rows(db, other, 5)
    await _add_rows(db, user, 1)

    ai = _client(db, FakeProvider(GOOD), ai_daily_limit_per_user=2)
    assert await ai.requests_today(user) == 1
    assert await _structured(ai, user) == GOOD
    with pytest.raises(AIDailyLimitError):
        await _structured(ai, user)


async def test_failed_requests_count_toward_limit(db: AsyncSession) -> None:
    user = await make_user(db)
    ai = _client(
        db,
        FakeProvider(ProviderOutputError("x"), ProviderOutputError("y")),
        ai_daily_limit_per_user=2,
    )
    with pytest.raises(AIOutputError):
        await _structured(ai, user)
    with pytest.raises(AIDailyLimitError):
        await _structured(ai, user)


# --- HTTP mapping (test-only route using the dependency) --------------------------


@pytest.fixture
def fake_ai(app: FastAPI) -> FakeProvider:
    fake = FakeProvider()
    app.state.llm_provider = fake

    async def route(user: CurrentUser, ai: AIClientDep) -> dict[str, Any]:
        return (await _structured(ai, user)).model_dump()

    app.add_api_route("/api/test-ai", route, methods=["GET"])
    return fake


async def test_http_success(client: AsyncClient, db: AsyncSession, fake_ai: FakeProvider) -> None:
    user = await make_user(db)
    await use_new_session(client, db, user)
    fake_ai.script(GOOD)

    r = await client.get("/api/test-ai")

    assert r.status_code == 200, r.text
    assert r.json() == {"title": "Fixed login", "hours": 2.5}


async def test_http_limit_returns_429(
    client: AsyncClient,
    db: AsyncSession,
    fake_ai: FakeProvider,
    settings_override: Callable[..., Settings],
) -> None:
    settings_override(ai_daily_limit_per_user=1)
    user = await make_user(db)
    await use_new_session(client, db, user)
    fake_ai.script(GOOD, GOOD)

    assert (await client.get("/api/test-ai")).status_code == 200
    r = await client.get("/api/test-ai")

    assert r.status_code == 429
    assert r.json()["error"]["code"] == "ai_daily_limit_exceeded"


async def test_http_disabled_returns_503(
    app: FastAPI, client: AsyncClient, db: AsyncSession, fake_ai: FakeProvider
) -> None:
    app.state.llm_provider = None
    user = await make_user(db)
    await use_new_session(client, db, user)

    r = await client.get("/api/test-ai")

    assert r.status_code == 503
    assert r.json()["error"]["code"] == "ai_disabled"


async def test_http_requires_login(client: AsyncClient, fake_ai: FakeProvider) -> None:
    assert (await client.get("/api/test-ai")).status_code == 401


# --- Factory ----------------------------------------------------------------------


def test_factory_disabled_when_provider_empty() -> None:
    assert build_provider(settings_with(llm_provider="")) is None


def test_factory_unknown_provider() -> None:
    with pytest.raises(AIConfigError, match="has no adapter"):
        build_provider(settings_with(llm_provider="acme", llm_api_key="k", llm_model="m"))


def test_factory_missing_key() -> None:
    with pytest.raises(AIConfigError, match="LLM_API_KEY"):
        build_provider(settings_with(llm_provider="openai", llm_api_key="", llm_model="m"))


def test_factory_missing_model() -> None:
    with pytest.raises(AIConfigError, match="LLM_MODEL"):
        build_provider(settings_with(llm_provider="openai", llm_api_key="k", llm_model=""))


async def test_factory_builds_openai_adapter() -> None:
    provider = build_provider(
        settings_with(
            llm_provider=" OpenAI ",
            llm_api_key="k",
            llm_model="some-model",
            llm_base_url="https://gw.example.test/v1",
        )
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert (provider.name, provider.model) == ("openai", "some-model")
    await provider.aclose()


def test_app_refuses_to_start_with_broken_ai_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(AIConfigError):
            create_app()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


# --- OpenAI-compatible adapter (MockTransport) ------------------------------------


def _completion(
    content: str | None, *, finish: str = "stop", refusal: str | None = None, usage: bool = True
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "kimi-test",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {"role": "assistant", "content": content, "refusal": refusal},
            }
        ],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    return body


def _adapter(*responses: httpx2.Response, seen: list[httpx2.Request]) -> OpenAICompatibleProvider:
    queue = list(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return queue.pop(0)

    return OpenAICompatibleProvider(
        api_key="sk-test-key",
        model="kimi-test",
        base_url="https://gw.example.test/v1",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )


async def test_adapter_structured_call() -> None:
    seen: list[httpx2.Request] = []
    adapter = _adapter(
        httpx2.Response(200, json=_completion('{"title": "Fixed login", "hours": 2.5}')),
        seen=seen,
    )

    result, usage = await adapter.generate_structured("Be helpful.", "note", Draft)

    assert result == GOOD
    assert usage == Usage(input_tokens=11, output_tokens=7)
    request = seen[0]
    assert str(request.url) == "https://gw.example.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-test-key"
    body = json.loads(request.content)
    assert body["model"] == "kimi-test"
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"]["additionalProperties"] is False
    system, user = body["messages"]
    assert system["role"] == "system"
    assert system["content"].startswith("Be helpful.")
    assert '"title"' in system["content"]  # schema repeated in the prompt
    assert user == {"role": "user", "content": "note"}


@pytest.mark.parametrize(
    "content",
    [
        '```json\n{"title": "Fixed login", "hours": 2.5}\n```',
        'Here you go: {"title": "Fixed login", "hours": 2.5}',
    ],
)
async def test_adapter_tolerates_wrapped_json(content: str) -> None:
    adapter = _adapter(httpx2.Response(200, json=_completion(content)), seen=[])
    result, _ = await adapter.generate_structured("s", "u", Draft)
    assert result == GOOD


@pytest.mark.parametrize(
    "body",
    [
        _completion("not json at all"),
        _completion('{"title": "x", "hours": 99}'),  # fails Field(le=24)
        _completion(None, refusal="I can't help with that"),
        _completion('{"title": "x"', finish="length"),
        _completion(""),
    ],
    ids=["invalid-json", "constraint", "refusal", "truncated", "empty"],
)
async def test_adapter_bad_output_raises_output_error_with_usage(body: dict[str, Any]) -> None:
    adapter = _adapter(httpx2.Response(200, json=body), seen=[])
    with pytest.raises(ProviderOutputError) as exc:
        await adapter.generate_structured("s", "u", Draft)
    assert exc.value.usage == Usage(input_tokens=11, output_tokens=7)


async def test_adapter_missing_usage_is_zero() -> None:
    adapter = _adapter(httpx2.Response(200, json=_completion("hi", usage=False)), seen=[])
    assert await adapter.generate_text("s", "u") == ("hi", Usage())


async def test_adapter_http_error_raises_call_error_without_vendor_message() -> None:
    adapter = _adapter(
        httpx2.Response(
            401, json={"error": {"message": "Incorrect API key provided: sk-tes***key"}}
        ),
        seen=[],
    )
    with pytest.raises(ProviderCallError) as exc:
        await adapter.generate_text("s", "u")
    assert str(exc.value) == "AuthenticationError (HTTP 401)"


async def test_adapter_falls_back_when_json_schema_unsupported() -> None:
    seen: list[httpx2.Request] = []
    adapter = _adapter(
        httpx2.Response(
            400, json={"error": {"message": "response_format json_schema is not supported"}}
        ),
        httpx2.Response(200, json=_completion('{"title": "Fixed login", "hours": 2.5}')),
        httpx2.Response(200, json=_completion('{"title": "Fixed login", "hours": 2.5}')),
        seen=seen,
    )

    assert (await adapter.generate_structured("s", "u", Draft))[0] == GOOD
    assert (await adapter.generate_structured("s", "u", Draft))[0] == GOOD

    formats = [json.loads(r.content)["response_format"]["type"] for r in seen]
    assert formats == ["json_schema", "json_object", "json_object"]


async def test_adapter_other_bad_request_is_not_downgraded() -> None:
    adapter = _adapter(
        httpx2.Response(400, json={"error": {"message": "context length exceeded"}}), seen=[]
    )
    with pytest.raises(ProviderCallError, match="BadRequestError"):
        await adapter.generate_structured("s", "u", Draft)


async def test_adapter_text_call() -> None:
    seen: list[httpx2.Request] = []
    adapter = _adapter(httpx2.Response(200, json=_completion("  Hello team.  ")), seen=seen)

    assert await adapter.generate_text("s", "u") == ("Hello team.", Usage(11, 7))
    assert "response_format" not in json.loads(seen[0].content)
