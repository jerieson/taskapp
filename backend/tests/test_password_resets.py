from collections.abc import Callable
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_token
from app.db.base import utcnow
from app.models import PasswordReset, Role
from tests.auth_helpers import PASSWORD, fetch_csrf, login, login_as
from tests.factories import make_user

pytestmark = pytest.mark.anyio

NEW_PASSWORD = "a-whole-new-pass"


def _token(reset_url: str) -> str:
    return reset_url.rsplit("/", 1)[1]


async def _generate(client: AsyncClient, user_id: int) -> str:
    resp = await client.post(f"/api/admin/users/{user_id}/password-reset")
    assert resp.status_code == 201, resp.text
    assert resp.json()["reset_url"].startswith("http://localhost:5173/reset-password/")
    return _token(resp.json()["reset_url"])


async def _use(client: AsyncClient, token: str, password: str = NEW_PASSWORD) -> object:
    if "csrf_token" not in client.cookies:
        await fetch_csrf(client)
    return await client.post(f"/api/password-resets/{token}", json={"new_password": password})


async def test_generate_stores_only_hash(client: AsyncClient, db: AsyncSession) -> None:
    admin = await login_as(client, db, role=Role.ADMIN)
    user = await make_user(db, password=PASSWORD)
    token = await _generate(client, user.id)

    reset = await db.scalar(select(PasswordReset).where(PasswordReset.user_id == user.id))
    assert reset is not None
    assert reset.token_hash == hash_token(token)
    assert reset.created_by == admin.id
    assert reset.expires_at > utcnow() + timedelta(hours=23)


async def test_generate_for_missing_or_inactive_user(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    assert (await client.post("/api/admin/users/999999/password-reset")).status_code == 404
    inactive = await make_user(db, is_active=False)
    resp = await client.post(f"/api/admin/users/{inactive.id}/password-reset")
    assert resp.status_code == 409


@pytest.mark.parametrize("role", [Role.MANAGER, Role.DEV])
async def test_non_admin_cannot_generate(client: AsyncClient, db: AsyncSession, role: Role) -> None:
    await login_as(client, db, role=role)
    target = await make_user(db)
    resp = await client.post(f"/api/admin/users/{target.id}/password-reset")
    assert resp.status_code == 403
    assert await db.scalar(select(PasswordReset)) is None


async def test_check_reset_link(
    client: AsyncClient, db: AsyncSession, new_client: Callable[[], AsyncClient]
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    user = await make_user(db, password=PASSWORD)
    token = await _generate(client, user.id)

    anon = new_client()
    resp = await anon.get(f"/api/password-resets/{token}")
    assert resp.status_code == 200
    assert resp.json()["valid"] is True
    assert resp.json()["username"] == user.username

    resp = await anon.get("/api/password-resets/bogus")
    assert resp.status_code == 200
    assert resp.json() == {"valid": False, "username": None, "expires_at": None}


async def test_reset_sets_password_and_revokes_sessions(
    client: AsyncClient, db: AsyncSession, new_client: Callable[[], AsyncClient]
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    user = await make_user(db, password=PASSWORD)
    users_browser = new_client()
    assert (await login(users_browser, user.username)).status_code == 200
    token = await _generate(client, user.id)

    resp = await _use(new_client(), token)
    assert resp.status_code == 204

    assert (await users_browser.get("/api/auth/me")).status_code == 401  # sessions revoked
    assert (await login(new_client(), user.username, PASSWORD)).status_code == 401
    assert (await login(new_client(), user.username, NEW_PASSWORD)).status_code == 200


async def test_reset_is_single_use(
    client: AsyncClient, db: AsyncSession, new_client: Callable[[], AsyncClient]
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    user = await make_user(db, password=PASSWORD)
    token = await _generate(client, user.id)

    assert (await _use(new_client(), token)).status_code == 204
    resp = await _use(new_client(), token, "yet-another-pass")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "reset_invalid"
    assert (await new_client().get(f"/api/password-resets/{token}")).json()["valid"] is False
    assert (await login(new_client(), user.username, NEW_PASSWORD)).status_code == 200


async def test_expired_reset_rejected(
    client: AsyncClient, db: AsyncSession, new_client: Callable[[], AsyncClient]
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    user = await make_user(db, password=PASSWORD)
    token = await _generate(client, user.id)
    reset = await db.scalar(select(PasswordReset).where(PasswordReset.user_id == user.id))
    assert reset is not None
    reset.expires_at = utcnow() - timedelta(seconds=1)
    await db.flush()

    assert (await new_client().get(f"/api/password-resets/{token}")).json()["valid"] is False
    assert (await _use(new_client(), token)).status_code == 404
    assert (await login(new_client(), user.username, PASSWORD)).status_code == 200


async def test_reset_validates_password(
    client: AsyncClient, db: AsyncSession, new_client: Callable[[], AsyncClient]
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    user = await make_user(db, password=PASSWORD)
    token = await _generate(client, user.id)
    resp = await _use(new_client(), token, "short")
    assert resp.status_code == 422
    assert "new_password" in resp.json()["error"]["fields"]
