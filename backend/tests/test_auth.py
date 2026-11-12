from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.core.rate_limit import LoginRateLimiter
from app.core.security import hash_token
from app.db.base import utcnow
from app.models import Role, UserSession
from tests.auth_helpers import PASSWORD, fetch_csrf, login, login_as, use_new_session
from tests.factories import make_user

pytestmark = pytest.mark.anyio


async def _sessions(db: AsyncSession, user_id: int) -> list[UserSession]:
    db.expire_all()
    return list(await db.scalars(select(UserSession).where(UserSession.user_id == user_id)))


# --- login / logout / me -------------------------------------------------------------


async def test_login_success_sets_cookies_and_returns_user(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await make_user(db, role=Role.MANAGER, password=PASSWORD)
    resp = await login(client, user.username)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == user.id
    assert body["role"] == "manager"
    assert body["team"]["id"] == user.team_id
    assert body["has_password"] is True
    assert "password_hash" not in body

    set_cookies = resp.headers.get_list("set-cookie")
    session_cookie = next(c for c in set_cookies if c.startswith("session="))
    csrf_cookie = next(c for c in set_cookies if c.startswith("csrf_token="))
    assert "HttpOnly" in session_cookie
    assert "samesite=lax" in session_cookie.lower()
    assert "Secure" not in session_cookie  # COOKIE_SECURE=false in tests
    assert "HttpOnly" not in csrf_cookie

    # Only the hash of the token is stored.
    token = client.cookies["session"]
    [row] = await _sessions(db, user.id)
    assert row.token_hash == hash_token(token)
    assert row.token_hash != token
    assert row.csrf_token == client.cookies["csrf_token"]

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == user.username


async def test_secure_cookie_flag_follows_setting(
    client: AsyncClient, db: AsyncSession, settings_override: Callable[..., object]
) -> None:
    settings_override(cookie_secure=True)
    client.base_url = "https://test"  # Secure cookies are only sent over HTTPS
    user = await make_user(db, password=PASSWORD)
    resp = await login(client, user.username)
    assert resp.status_code == 200
    for cookie in resp.headers.get_list("set-cookie"):
        assert "Secure" in cookie


@pytest.mark.parametrize(
    ("username", "password"),
    [("nobody", PASSWORD), (None, "wrong-password")],
    ids=["unknown-user", "wrong-password"],
)
async def test_login_failure(
    client: AsyncClient, db: AsyncSession, username: str | None, password: str
) -> None:
    user = await make_user(db, password=PASSWORD)
    resp = await login(client, username or user.username, password)
    assert resp.status_code == 401
    assert resp.json() == {
        "error": {"code": "invalid_credentials", "message": "Invalid username or password"}
    }
    assert "session" not in client.cookies
    assert await _sessions(db, user.id) == []


async def test_login_inactive_user_blocked(client: AsyncClient, db: AsyncSession) -> None:
    user = await make_user(db, password=PASSWORD, is_active=False)
    resp = await login(client, user.username)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


async def test_google_only_user_cannot_password_login(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await make_user(db, password_hash=None, google_sub="g-123")
    resp = await login(client, user.username, "anything-at-all")
    assert resp.status_code == 401


async def test_me_requires_login(client: AsyncClient) -> None:
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "not_authenticated"


async def test_session_rejected_after_user_deactivated(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await login_as(client, db)
    user.is_active = False
    await db.flush()
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_expired_session_rejected(client: AsyncClient, db: AsyncSession) -> None:
    user = await login_as(client, db)
    [row] = await _sessions(db, user.id)
    row.expires_at = utcnow() - timedelta(seconds=1)
    await db.flush()
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_forged_session_cookie_rejected(client: AsyncClient) -> None:
    client.cookies.set("session", "not-a-real-token")
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_logout_revokes_session(client: AsyncClient, db: AsyncSession) -> None:
    user = await login_as(client, db)
    stolen_token = client.cookies["session"]

    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 204
    assert "session" not in client.cookies
    [row] = await _sessions(db, user.id)
    assert row.revoked_at is not None

    # The old token no longer works even if replayed.
    client.cookies.set("session", stolen_token)
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_login_replaces_previous_session_of_same_browser(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await login_as(client, db)
    resp = await login(client, user.username)
    assert resp.status_code == 200
    sessions = await _sessions(db, user.id)
    assert len(sessions) == 2
    assert sum(s.revoked_at is None for s in sessions) == 1


# --- CSRF ----------------------------------------------------------------------------


async def test_csrf_endpoint_sets_readable_cookie(client: AsyncClient) -> None:
    resp = await client.get("/api/auth/csrf")
    assert resp.status_code == 200
    assert resp.json()["csrf_token"] == client.cookies["csrf_token"]
    # Reuses an existing token instead of rotating it.
    again = await client.get("/api/auth/csrf")
    assert again.json()["csrf_token"] == resp.json()["csrf_token"]


async def test_login_without_csrf_token_rejected(client: AsyncClient, db: AsyncSession) -> None:
    user = await make_user(db, password=PASSWORD)
    resp = await client.post(
        "/api/auth/login", json={"username": user.username, "password": PASSWORD}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


async def test_login_with_mismatched_csrf_token_rejected(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await make_user(db, password=PASSWORD)
    await fetch_csrf(client)
    client.headers["X-CSRF-Token"] = "something-else"
    resp = await client.post(
        "/api/auth/login", json={"username": user.username, "password": PASSWORD}
    )
    assert resp.status_code == 403


@pytest.mark.parametrize("header", [None, "wrong-token"], ids=["missing", "wrong"])
async def test_authenticated_non_get_requires_csrf(
    client: AsyncClient, db: AsyncSession, header: str | None
) -> None:
    await login_as(client, db)
    if header is None:
        del client.headers["X-CSRF-Token"]
    else:
        client.headers["X-CSRF-Token"] = header
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"
    # GET requests do not need the header.
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_csrf_token_must_match_the_session(client: AsyncClient, db: AsyncSession) -> None:
    """A cookie+header pair that matches each other but not the session is rejected
    (e.g. a csrf_token cookie planted by an attacker)."""
    await login_as(client, db)
    client.cookies.set("csrf_token", "planted")
    client.headers["X-CSRF-Token"] = "planted"
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 403


# --- change password -----------------------------------------------------------------


async def test_change_password_requires_correct_current_password(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login_as(client, db)
    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong-password", "new_password": "brand-new-pass"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_current_password"
    assert "current_password" in resp.json()["error"]["fields"]


async def test_change_password_revokes_other_sessions(
    client: AsyncClient, db: AsyncSession, new_client: Callable[[], AsyncClient]
) -> None:
    user = await login_as(client, db)
    other = new_client()
    assert (await login(other, user.username)).status_code == 200

    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "brand-new-pass"},
    )
    assert resp.status_code == 204

    assert (await client.get("/api/auth/me")).status_code == 200  # current session kept
    assert (await other.get("/api/auth/me")).status_code == 401  # other session revoked

    fresh = new_client()
    assert (await login(fresh, user.username, PASSWORD)).status_code == 401
    assert (await login(fresh, user.username, "brand-new-pass")).status_code == 200


async def test_change_password_validates_new_password(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login_as(client, db)
    resp = await client.post(
        "/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "short"}
    )
    assert resp.status_code == 422
    assert "new_password" in resp.json()["error"]["fields"]


async def test_change_password_for_google_only_user(client: AsyncClient, db: AsyncSession) -> None:
    user = await make_user(db, password_hash=None, google_sub="g-1")
    await use_new_session(client, db, user)
    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": "whatever", "new_password": "brand-new-pass"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "password_not_set"


# --- rate limiting -------------------------------------------------------------------


async def test_login_rate_limited_per_ip(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    app.state.login_limiter = LoginRateLimiter(max_failures=3)
    user = await make_user(db, password=PASSWORD)
    for _ in range(3):
        assert (await login(client, user.username, "wrong-password")).status_code == 401

    blocked = await login(client, user.username, PASSWORD)  # even the right password
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "too_many_login_attempts"
    assert int(blocked.headers["retry-after"]) > 0


async def test_rate_limit_ignores_cf_header_unless_trusted(
    app: FastAPI, client: AsyncClient, db: AsyncSession, settings_override: Callable[..., object]
) -> None:
    limiter = LoginRateLimiter(max_failures=1)
    app.state.login_limiter = limiter
    user = await make_user(db, password=PASSWORD)

    # Untrusted: a spoofed CF-Connecting-IP does not give a fresh allowance.
    client.headers["CF-Connecting-IP"] = "203.0.113.1"
    assert (await login(client, user.username, "wrong")).status_code == 401
    client.headers["CF-Connecting-IP"] = "203.0.113.2"
    assert (await login(client, user.username, PASSWORD)).status_code == 429

    # Trusted (behind cloudflared): each client IP is limited separately.
    settings_override(trust_proxy_headers=True)
    app.state.login_limiter = LoginRateLimiter(max_failures=1)
    client.headers["CF-Connecting-IP"] = "203.0.113.1"
    assert (await login(client, user.username, "wrong")).status_code == 401
    assert (await login(client, user.username, PASSWORD)).status_code == 429
    client.headers["CF-Connecting-IP"] = "203.0.113.2"
    assert (await login(client, user.username, PASSWORD)).status_code == 200


def test_rate_limiter_window_expires() -> None:
    now = [1000.0]
    limiter = LoginRateLimiter(max_failures=2, window_seconds=60, clock=lambda: now[0])
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    with pytest.raises(Exception, match="Too many"):
        limiter.check("1.2.3.4")
    limiter.check("5.6.7.8")  # other IPs unaffected
    now[0] += 61
    limiter.check("1.2.3.4")


# --- require_role --------------------------------------------------------------------


@pytest.fixture
def role_app(app: FastAPI) -> FastAPI:
    from fastapi import Depends

    @app.get("/api/_test/managers-only", dependencies=[Depends(require_role(Role.MANAGER))])
    async def managers_only() -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.mark.parametrize(
    ("role", "expected"), [(Role.MANAGER, 200), (Role.DEV, 403), (Role.ADMIN, 403)]
)
async def test_require_role(
    role_app: FastAPI, client: AsyncClient, db: AsyncSession, role: Role, expected: int
) -> None:
    await login_as(client, db, role=role)
    resp = await client.get("/api/_test/managers-only")
    assert resp.status_code == expected
    if expected == 403:
        assert resp.json()["error"]["code"] == "forbidden"
