"""Google OAuth. The network exchange is replaced by FakeGoogle (callback tests) or an
httpx2 MockTransport (client wrapper tests); no real Google calls are made."""

import json
from collections.abc import Callable
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx2
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import generate_token, hash_token
from app.db.base import utcnow
from app.models import Invite, Role, User
from app.services.google import (
    GoogleOAuthClient,
    GoogleOAuthError,
    GoogleUserInfo,
    get_google_client,
)
from tests.conftest import settings_with
from tests.factories import make_team, make_user

pytestmark = pytest.mark.anyio

FRONTEND = "http://localhost:5173"


class FakeGoogle:
    def __init__(self) -> None:
        self.info: GoogleUserInfo | None = None
        self.calls: list[tuple[str, str]] = []

    def authorization_url(self, state: str, code_verifier: str) -> str:
        return f"https://accounts.google.test/auth?state={state}"

    async def fetch_user_info(self, code: str, code_verifier: str) -> GoogleUserInfo:
        self.calls.append((code, code_verifier))
        if self.info is None:
            raise GoogleOAuthError("exchange failed")
        return self.info


@pytest.fixture
def google(app: FastAPI, settings_override: Callable[..., Settings]) -> FakeGoogle:
    settings_override(google_client_id="client-id", google_client_secret="client-secret")
    fake = FakeGoogle()
    app.dependency_overrides[get_google_client] = lambda: fake
    return fake


async def _google_flow(
    client: AsyncClient,
    google: FakeGoogle,
    info: GoogleUserInfo | None,
    invite: str | None = None,
) -> str:
    """Run login -> callback and return the final redirect location."""
    google.info = info
    params = {"invite": invite} if invite else {}
    start = await client.get("/api/auth/google/login", params=params)
    assert start.status_code == 302
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    resp = await client.get("/api/auth/google/callback", params={"code": "c0de", "state": state})
    assert resp.status_code == 302
    return resp.headers["location"]


def _info(email: str, sub: str = "google-sub-1", verified: bool = True) -> GoogleUserInfo:
    return GoogleUserInfo(sub=sub, email=email, email_verified=verified)


async def _invite(db: AsyncSession, email: str, role: Role = Role.DEV) -> tuple[Invite, str]:
    admin = await make_user(db, role=Role.ADMIN)
    team = await make_team(db)
    token = generate_token()
    invite = Invite(
        email=email,
        role=role,
        team_id=team.id,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(hours=1),
        created_by=admin.id,
    )
    db.add(invite)
    await db.flush()
    return invite, token


async def test_unknown_email_rejected(
    client: AsyncClient, db: AsyncSession, google: FakeGoogle
) -> None:
    location = await _google_flow(client, google, _info("stranger@example.com"))
    assert location == f"{FRONTEND}/login?error=google_account_not_found"
    assert "session" not in client.cookies
    assert await db.scalar(select(User).where(User.email == "stranger@example.com")) is None


async def test_unverified_email_rejected(
    client: AsyncClient, db: AsyncSession, google: FakeGoogle
) -> None:
    user = await make_user(db, email="real@example.com")
    location = await _google_flow(client, google, _info(user.email, verified=False))
    assert location == f"{FRONTEND}/login?error=google_email_unverified"
    assert "session" not in client.cookies
    await db.refresh(user)
    assert user.google_sub is None


async def test_invite_email_accepted(
    client: AsyncClient, db: AsyncSession, google: FakeGoogle
) -> None:
    invite, token = await _invite(db, "invited@example.com", Role.MANAGER)

    location = await _google_flow(client, google, _info("Invited@Example.com"), invite=token)

    assert location == f"{FRONTEND}/"
    me = (await client.get("/api/auth/me")).json()
    assert me["email"] == "invited@example.com"
    assert me["role"] == "manager"
    assert me["team"]["id"] == invite.team_id
    assert me["google_linked"] is True
    assert me["has_password"] is False
    assert me["username"] == "invited"
    await db.refresh(invite)
    assert invite.accepted_at is not None


async def test_pending_invite_accepted_without_invite_link(
    client: AsyncClient, db: AsyncSession, google: FakeGoogle
) -> None:
    await _invite(db, "direct@example.com")
    location = await _google_flow(client, google, _info("direct@example.com"))
    assert location == f"{FRONTEND}/"
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_expired_invite_not_accepted(
    client: AsyncClient, db: AsyncSession, google: FakeGoogle
) -> None:
    invite, token = await _invite(db, "late@example.com")
    invite.expires_at = utcnow() - timedelta(seconds=1)
    await db.flush()
    location = await _google_flow(client, google, _info("late@example.com"), invite=token)
    assert location == f"{FRONTEND}/login?error=invite_invalid"


async def test_invite_link_requires_matching_email(
    client: AsyncClient, db: AsyncSession, google: FakeGoogle
) -> None:
    _, token = await _invite(db, "invited@example.com")
    location = await _google_flow(client, google, _info("someone-else@example.com"), invite=token)
    assert location == f"{FRONTEND}/login?error=invite_email_mismatch"
    assert "session" not in client.cookies


async def test_generated_username_avoids_collisions(
    client: AsyncClient, db: AsyncSession, google: FakeGoogle
) -> None:
    await make_user(db, username="dup")
    _, token = await _invite(db, "dup@example.com")
    assert await _google_flow(client, google, _info("dup@example.com"), invite=token) == (
        f"{FRONTEND}/"
    )
    assert (await client.get("/api/auth/me")).json()["username"] == "dup-2"


async def test_existing_account_linked(
    client: AsyncClient, db: AsyncSession, google: FakeGoogle
) -> None:
    user = await make_user(db, email="pat@example.com", password="pw-12345678")

    location = await _google_flow(client, google, _info("PAT@example.com", sub="sub-pat"))

    assert location == f"{FRONTEND}/"
    me = (await client.get("/api/auth/me")).json()
    assert me["id"] == user.id
    assert me["google_linked"] is True
    assert me["has_password"] is True
    await db.refresh(user)
    assert user.google_sub == "sub-pat"


async def test_linked_account_logs_in_by_sub(
    client: AsyncClient, db: AsyncSession, google: FakeGoogle
) -> None:
    user = await make_user(db, email="old@example.com", google_sub="sub-stable")
    # The Google email changed since linking; the stable `sub` still identifies the user.
    location = await _google_flow(client, google, _info("new@example.com", sub="sub-stable"))
    assert location == f"{FRONTEND}/"
    assert (await client.get("/api/auth/me")).json()["id"] == user.id


async def test_inactive_user_rejected(
    client: AsyncClient, db: AsyncSession, google: FakeGoogle
) -> None:
    await make_user(db, email="gone@example.com", is_active=False)
    location = await _google_flow(client, google, _info("gone@example.com"))
    assert location == f"{FRONTEND}/login?error=account_inactive"


async def test_email_linked_to_other_google_account_rejected(
    client: AsyncClient, db: AsyncSession, google: FakeGoogle
) -> None:
    await make_user(db, email="taken@example.com", google_sub="sub-original")
    location = await _google_flow(client, google, _info("taken@example.com", sub="sub-other"))
    assert location == f"{FRONTEND}/login?error=google_account_conflict"


async def test_state_mismatch_rejected(
    client: AsyncClient, db: AsyncSession, google: FakeGoogle
) -> None:
    user = await make_user(db, email="pat@example.com")
    google.info = _info(user.email)
    await client.get("/api/auth/google/login")
    resp = await client.get("/api/auth/google/callback", params={"code": "c0de", "state": "forged"})
    assert resp.headers["location"] == f"{FRONTEND}/login?error=google_state_invalid"
    assert google.calls == []  # never exchanged the code


async def test_callback_without_state_cookie_rejected(
    client: AsyncClient, google: FakeGoogle
) -> None:
    resp = await client.get("/api/auth/google/callback", params={"code": "c", "state": "s"})
    assert resp.headers["location"] == f"{FRONTEND}/login?error=google_state_invalid"


async def test_user_cancelled_at_google(client: AsyncClient, google: FakeGoogle) -> None:
    start = await client.get("/api/auth/google/login")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    resp = await client.get(
        "/api/auth/google/callback", params={"error": "access_denied", "state": state}
    )
    assert resp.headers["location"] == f"{FRONTEND}/login?error=google_cancelled"


async def test_exchange_failure(client: AsyncClient, google: FakeGoogle) -> None:
    location = await _google_flow(client, google, None)
    assert location == f"{FRONTEND}/login?error=google_failed"


async def test_google_not_configured(client: AsyncClient) -> None:
    resp = await client.get("/api/auth/google/login")
    assert resp.status_code == 302
    assert resp.headers["location"] == f"{FRONTEND}/login?error=google_not_configured"


# --- GoogleOAuthClient (the Authlib wrapper) ------------------------------------------


def _settings() -> Settings:
    return settings_with(google_client_id="cid", google_client_secret="csecret")


def test_authorization_url_uses_pkce() -> None:
    url = GoogleOAuthClient(_settings()).authorization_url("st4te", "v" * 43)
    query = parse_qs(urlparse(url).query)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert query["client_id"] == ["cid"]
    assert query["state"] == ["st4te"]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"]
    assert set(query["scope"][0].split()) == {"openid", "email", "profile"}
    assert query["redirect_uri"] == ["http://localhost:5173/api/auth/google/callback"]


async def test_fetch_user_info_exchanges_code() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "oauth2.googleapis.com":
            seen["token_body"] = request.content.decode()
            return httpx2.Response(
                200, json={"access_token": "at", "token_type": "Bearer", "expires_in": 3600}
            )
        seen["auth"] = request.headers["authorization"]
        return httpx2.Response(
            200, json={"sub": "123", "email": "a@example.com", "email_verified": True}
        )

    client = GoogleOAuthClient(_settings(), transport=httpx2.MockTransport(handler))
    info = await client.fetch_user_info("the-code", "the-verifier")

    assert info == GoogleUserInfo(sub="123", email="a@example.com", email_verified=True)
    body = parse_qs(seen["token_body"])
    assert body["code"] == ["the-code"]
    assert body["code_verifier"] == ["the-verifier"]
    assert seen["auth"] == "Bearer at"


async def test_fetch_user_info_error_is_wrapped() -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(400, content=json.dumps({"error": "invalid_grant"}))

    client = GoogleOAuthClient(_settings(), transport=httpx2.MockTransport(handler))
    with pytest.raises(GoogleOAuthError):
        await client.fetch_user_info("bad", "verifier")
