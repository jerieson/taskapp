"""The one entry point AI features use to call the LLM.

Wraps the configured provider with:
- the per-user daily limit (AI_DAILY_LIMIT_PER_USER, counted in APP_TIMEZONE days) -> 429
- Pydantic validation of structured output, retried once, then AIOutputError
- an ai_requests row for every provider call, successful or not (a retry is a second
  call, so it writes a second row and counts toward the limit)

Rows are committed immediately so they survive a failed feature request. Call the
client before making other changes in the same session.

The limit is a soft cap: two requests racing at the limit can both pass. That is
acceptable for a handful of users and avoids holding a lock across a slow LLM call.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, time
from typing import Annotated

from fastapi import Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AIDailyLimitError, AIDisabledError, AIOutputError, AIProviderError
from app.ai.providers.base import (
    LLMProvider,
    ProviderCallError,
    ProviderError,
    ProviderOutputError,
    Usage,
)
from app.core.config import Settings, SettingsDep
from app.db.session import SessionDep
from app.models.ai import AIRequest
from app.models.enums import AIFeature
from app.models.user import User

logger = logging.getLogger("app.ai")

# One initial attempt plus one retry when the output fails validation.
STRUCTURED_ATTEMPTS = 2


class AIClient:
    def __init__(
        self, provider: LLMProvider | None, session: AsyncSession, settings: Settings
    ) -> None:
        self._provider = provider
        self._session = session
        self._settings = settings

    @property
    def provider(self) -> LLMProvider:
        if self._provider is None:
            raise AIDisabledError()
        return self._provider

    async def generate_structured[T: BaseModel](
        self, user: User, feature: AIFeature, *, system: str, prompt: str, schema: type[T]
    ) -> T:
        provider = self.provider
        await self._check_limit(user)

        async def call() -> tuple[T, Usage]:
            result, usage = await provider.generate_structured(system, prompt, schema)
            if not isinstance(result, schema):  # adapters must return the schema type
                raise ProviderOutputError(f"Adapter returned {type(result).__name__}", usage)
            return result, usage

        for attempt in range(1, STRUCTURED_ATTEMPTS + 1):
            try:
                return await self._logged_call(user, feature, provider, call)
            except ProviderOutputError as exc:
                logger.warning(
                    "AI output failed validation",
                    extra={"fields": {"feature": feature, "attempt": attempt, "error": str(exc)}},
                )
        raise AIOutputError()

    async def generate_text(
        self, user: User, feature: AIFeature, *, system: str, prompt: str
    ) -> str:
        provider = self.provider
        await self._check_limit(user)
        try:
            return await self._logged_call(
                user, feature, provider, lambda: provider.generate_text(system, prompt)
            )
        except ProviderOutputError as exc:
            raise AIOutputError() from exc

    async def requests_today(self, user: User) -> int:
        start = datetime.combine(datetime.now(self._settings.tz).date(), time())
        start_utc = start.replace(tzinfo=self._settings.tz).astimezone(UTC)
        count = await self._session.scalar(
            select(func.count())
            .select_from(AIRequest)
            .where(AIRequest.user_id == user.id, AIRequest.created_at >= start_utc)
        )
        return count or 0

    async def _check_limit(self, user: User) -> None:
        limit = self._settings.ai_daily_limit_per_user
        if await self.requests_today(user) >= limit:
            raise AIDailyLimitError(limit)

    async def _logged_call[R](
        self,
        user: User,
        feature: AIFeature,
        provider: LLMProvider,
        call: Callable[[], Awaitable[tuple[R, Usage]]],
    ) -> R:
        """Run one provider call and record it. Call errors become AIProviderError;
        output errors are re-raised for the caller to retry or convert."""
        try:
            result, usage = await call()
        except ProviderCallError as exc:
            await self._record(user, feature, provider, exc.usage, success=False)
            logger.error(
                "AI provider call failed",
                extra={"fields": {"feature": feature, "error": str(exc)}},
            )
            raise AIProviderError() from exc
        except ProviderError as exc:
            await self._record(user, feature, provider, exc.usage, success=False)
            raise
        except Exception:
            await self._record(user, feature, provider, Usage(), success=False)
            raise
        await self._record(user, feature, provider, usage, success=True)
        return result

    async def _record(
        self, user: User, feature: AIFeature, provider: LLMProvider, usage: Usage, *, success: bool
    ) -> None:
        self._session.add(
            AIRequest(
                user_id=user.id,
                feature=feature,
                provider=provider.name,
                model=provider.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                success=success,
            )
        )
        await self._session.commit()


def get_ai_client(request: Request, session: SessionDep, settings: SettingsDep) -> AIClient:
    return AIClient(request.app.state.llm_provider, session, settings)


AIClientDep = Annotated[AIClient, Depends(get_ai_client)]
