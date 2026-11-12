from collections.abc import Callable
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_token
from app.db.base import utcnow
from app.models import Invite, Role, User
from tests.auth_helpers import PASSWORD, fetch_csrf, login, login_as
from tests.factories import make_team, make_user

pytestmark = pytest.mark.anyio


def _token(invite_url: str) -> str:
    return invite_url.rsplit("/", 1)[1]


async def _create(client: AsyncClient, email: str, team_id: int, role: str = "dev") -> dict:
    resp = await client.post(
        "/api/admin/invites", json={"email": email, "role": role, "team_id": team_id}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _accept(client: AsyncClient, token: str, username: str = "newbie") -> object:
    if "csrf_token" not in client.cookies:
        await fetch_csrf(client)
    return await client.post(
        f"/api/invites/{token}/accept", json={"username": username, "password": PASSWORD}
    )


async def test_create_invite(client: AsyncClient, db: AsyncSession) -> None:
    admin = await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)

    body = await _create(client, "  New.Person@Example.COM ", team.id, "manager")

    assert body["email"] == "new.person@example.com"  # normalised
    assert body["role"] == "manager"
    assert body["status"] == "pending"
    assert body["created_by"] == admin.id
    assert body["invite_url"].startswith("http://localhost:5173/invite/")
    # Only the token hash is stored.
    invite = await db.get(Invite, body["id"])
    assert invite is not None
    assert invite.token_hash == hash_token(_token(body["invite_url"]))
    assert invite.expires_at > utcnow() + timedelta(hours=71)


async def test_create_invite_validation(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)

    resp = await client.post(
        "/api/admin/invites", json={"email": "x@example.com", "role": "admin", "team_id": team.id}
    )
    assert resp.status_code == 422
    assert "role" in resp.json()["error"]["fields"]

    resp = await client.post(
        "/api/admin/invites", json={"email": "not-an-email", "role": "dev", "team_id": team.id}
    )
    assert resp.status_code == 422
    assert "email" in resp.json()["error"]["fields"]

    resp = await client.post(
        "/api/admin/invites", json={"email": "x@example.com", "role": "dev", "team_id": 999999}
    )
    assert resp.status_code == 422
    assert "team_id" in resp.json()["error"]["fields"]


async def test_duplicate_email_rejected(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    existing = await make_user(db, email="taken@example.com")

    resp = await client.post(
        "/api/admin/invites",
        json={"email": existing.email.upper(), "role": "dev", "team_id": team.id},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "email_taken"

    await _create(client, "pending@example.com", team.id)
    resp = await client.post(
        "/api/admin/invites",
        json={"email": "Pending@example.com", "role": "dev", "team_id": team.id},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invite_pending"


async def test_expired_invite_does_not_block_a_new_one(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    body = await _create(client, "again@example.com", team.id)
    invite = await db.get(Invite, body["id"])
    assert invite is not None
    invite.expires_at = utcnow() - timedelta(minutes=1)
    await db.flush()

    await _create(client, "again@example.com", team.id)


@pytest.mark.parametrize("role", [Role.MANAGER, Role.DEV])
async def test_non_admin_cannot_manage_invites(
    client: AsyncClient, db: AsyncSession, role: Role
) -> None:
    await login_as(client, db, role=role)
    team = await make_team(db)
    resp = await client.post(
        "/api/admin/invites", json={"email": "x@example.com", "role": "dev", "team_id": team.id}
    )
    assert resp.status_code == 403
    assert (await client.get("/api/admin/invites")).status_code == 403
    assert (await client.delete("/api/admin/invites/1")).status_code == 403


async def test_admin_endpoints_require_login(client: AsyncClient) -> None:
    await fetch_csrf(client)
    assert (await client.get("/api/admin/invites")).status_code == 401
    resp = await client.post(
        "/api/admin/invites", json={"email": "x@example.com", "role": "dev", "team_id": 1}
    )
    assert resp.status_code == 401


async def test_list_invites_paginated_with_status(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    for i in range(3):
        await _create(client, f"list{i}@example.com", team.id)

    resp = await client.get("/api/admin/invites", params={"limit": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert len(body["items"]) == 2
    assert {i["status"] for i in body["items"]} == {"pending"}
    assert "invite_url" not in body["items"][0]
    assert "token_hash" not in body["items"][0]


async def test_public_invite_details(
    client: AsyncClient, db: AsyncSession, new_client: Callable[[], AsyncClient]
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db, name="Platform")
    body = await _create(client, "details@example.com", team.id)

    anon = new_client()
    resp = await anon.get(f"/api/invites/{_token(body['invite_url'])}")
    assert resp.status_code == 200
    assert resp.json()["email"] == "details@example.com"
    assert resp.json()["team_name"] == "Platform"

    resp = await anon.get("/api/invites/unknown-token")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "invite_invalid"


async def test_accept_invite_creates_user_and_logs_in(
    client: AsyncClient, db: AsyncSession, new_client: Callable[[], AsyncClient]
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    body = await _create(client, "joiner@example.com", team.id, "manager")

    anon = new_client()
    resp = await _accept(anon, _token(body["invite_url"]), "joiner")
    assert resp.status_code == 201, resp.text
    me = resp.json()
    assert me["username"] == "joiner"
    assert me["email"] == "joiner@example.com"  # fixed to the invite email
    assert me["role"] == "manager"
    assert me["team"]["id"] == team.id
    assert (await anon.get("/api/auth/me")).status_code == 200  # logged in

    invite = await db.get(Invite, body["id"])
    assert invite is not None
    await db.refresh(invite)
    assert invite.accepted_at is not None

    # The new password works for a normal login.
    assert (await login(new_client(), "joiner")).status_code == 200


async def test_invite_reuse_rejected(
    client: AsyncClient, db: AsyncSession, new_client: Callable[[], AsyncClient]
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    token = _token((await _create(client, "once@example.com", team.id))["invite_url"])

    assert (await _accept(new_client(), token, "first")).status_code == 201
    resp = await _accept(new_client(), token, "second")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "invite_invalid"
    assert (await new_client().get(f"/api/invites/{token}")).status_code == 404
    assert await db.scalar(select(User).where(User.username == "second")) is None


async def test_expired_invite_rejected(
    client: AsyncClient, db: AsyncSession, new_client: Callable[[], AsyncClient]
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    body = await _create(client, "late@example.com", team.id)
    invite = await db.get(Invite, body["id"])
    assert invite is not None
    invite.expires_at = utcnow() - timedelta(seconds=1)
    await db.flush()

    resp = await _accept(new_client(), _token(body["invite_url"]), "late")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "invite_invalid"


async def test_accept_rejects_taken_username(
    client: AsyncClient, db: AsyncSession, new_client: Callable[[], AsyncClient]
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    await make_user(db, username="taken")
    body = await _create(client, "someone@example.com", team.id)

    resp = await _accept(new_client(), _token(body["invite_url"]), "taken")
    assert resp.status_code == 409
    assert resp.json()["error"]["fields"] == {"username": "This username is already taken"}


async def test_accept_requires_csrf(
    client: AsyncClient, db: AsyncSession, new_client: Callable[[], AsyncClient]
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    token = _token((await _create(client, "csrf@example.com", team.id))["invite_url"])
    resp = await new_client().post(
        f"/api/invites/{token}/accept", json={"username": "csrfuser", "password": PASSWORD}
    )
    assert resp.status_code == 403


async def test_revoke_invite(
    client: AsyncClient, db: AsyncSession, new_client: Callable[[], AsyncClient]
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    pending = await _create(client, "revoke@example.com", team.id)
    accepted = await _create(client, "accepted@example.com", team.id)
    assert (await _accept(new_client(), _token(accepted["invite_url"]), "acc")).status_code == 201

    assert (await client.delete(f"/api/admin/invites/{pending['id']}")).status_code == 204
    assert (
        await new_client().get(f"/api/invites/{_token(pending['invite_url'])}")
    ).status_code == 404

    resp = await client.delete(f"/api/admin/invites/{accepted['id']}")
    assert resp.status_code == 409
    assert (await client.delete("/api/admin/invites/999999")).status_code == 404
