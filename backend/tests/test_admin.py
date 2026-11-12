"""Admin: teams, users, invite links. Every /api/admin endpoint is admin-only."""

import re

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Invite, Role, Team, User, UserSession
from tests.auth_helpers import PASSWORD, login, login_as
from tests.factories import make_log, make_team, make_user

pytestmark = pytest.mark.anyio


def _admin_routes(app: FastAPI) -> list[tuple[str, str]]:
    """Every (METHOD, path) under /api/admin, from the OpenAPI contract."""
    routes = []
    for path, ops in app.openapi()["paths"].items():
        if path.startswith("/api/admin"):
            concrete = re.sub(r"\{[^}]+\}", "1", path)
            routes.extend((method.upper(), concrete) for method in ops)
    return routes


# ---------------------------------------------------------------- access control


@pytest.mark.parametrize("role", [Role.MANAGER, Role.DEV])
async def test_non_admin_forbidden_on_every_admin_endpoint(
    app: FastAPI, client: AsyncClient, db: AsyncSession, role: Role
) -> None:
    await login_as(client, db, role=role)
    routes = _admin_routes(app)
    assert len(routes) >= 12  # teams, users, invites
    for method, path in routes:
        resp = await client.request(method, path, json={})
        assert resp.status_code in (403, 404), (method, path, resp.status_code)
        assert resp.json()["error"]["code"] in ("forbidden", "not_found")


async def test_admin_endpoints_require_login(app: FastAPI, client: AsyncClient) -> None:
    for method, path in _admin_routes(app):
        if method == "GET":
            assert (await client.get(path)).status_code == 401, path


# ---------------------------------------------------------------- teams


async def test_team_crud(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)

    resp = await client.post("/api/admin/teams", json={"name": "  Platform  "})
    assert resp.status_code == 201, resp.text
    team = resp.json()
    assert team["name"] == "Platform"
    assert team["member_count"] == 0

    resp = await client.patch(f"/api/admin/teams/{team['id']}", json={"name": "Platform Core"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Platform Core"

    resp = await client.get("/api/admin/teams")
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()["items"]]
    assert "Platform Core" in names

    assert (await client.delete(f"/api/admin/teams/{team['id']}")).status_code == 204
    assert await db.get(Team, team["id"]) is None
    assert (await client.delete(f"/api/admin/teams/{team['id']}")).status_code == 404


async def test_team_list_member_count(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db, name="Zzz counted")
    await make_user(db, team=team)
    await make_user(db, team=team, is_active=False)

    resp = await client.get("/api/admin/teams", params={"limit": 200})
    row = next(t for t in resp.json()["items"] if t["id"] == team.id)
    assert row["member_count"] == 2


async def test_team_name_unique_case_insensitive(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    await make_team(db, name="Mobile")
    other = await make_team(db, name="Web")

    resp = await client.post("/api/admin/teams", json={"name": "mobile"})
    assert resp.status_code == 409
    assert resp.json()["error"]["fields"]["name"]

    resp = await client.patch(f"/api/admin/teams/{other.id}", json={"name": "MOBILE"})
    assert resp.status_code == 409

    # Renaming to its own name (different case) is fine.
    resp = await client.patch(f"/api/admin/teams/{other.id}", json={"name": "WEB"})
    assert resp.status_code == 200

    resp = await client.post("/api/admin/teams", json={"name": "   "})
    assert resp.status_code == 422


async def test_team_delete_blocked_by_users(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    await make_user(db, team=team, is_active=False)

    resp = await client.delete(f"/api/admin/teams/{team.id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "team_in_use"


async def test_team_delete_blocked_by_prod_logs(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    old_team = await make_team(db)
    new_team = await make_team(db)
    author = await make_user(db, team=old_team)
    await make_log(db, user=author)  # snapshot team_id = old_team
    author.team_id = new_team.id
    await db.flush()

    resp = await client.delete(f"/api/admin/teams/{old_team.id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "team_in_use"


async def test_team_delete_removes_its_invites(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    resp = await client.post(
        "/api/admin/invites", json={"email": "gone@example.com", "role": "dev", "team_id": team.id}
    )
    invite_id = resp.json()["id"]

    assert (await client.delete(f"/api/admin/teams/{team.id}")).status_code == 204
    db.expire_all()
    assert await db.get(Invite, invite_id) is None


# ---------------------------------------------------------------- users


async def test_list_users_with_filters(client: AsyncClient, db: AsyncSession) -> None:
    admin = await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    manager = await make_user(db, role=Role.MANAGER, team=team)
    dev = await make_user(db, team=team)
    gone = await make_user(db, team=team, is_active=False)
    await make_user(db)  # another team

    resp = await client.get("/api/admin/users", params={"team_id": team.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    # Active users first.
    assert [u["id"] for u in body["items"]][-1] == gone.id
    first = body["items"][0]
    assert first["team"] == {"id": team.id, "name": team.name}
    assert set(first) >= {"is_active", "has_password", "google_linked", "email", "role"}

    resp = await client.get("/api/admin/users", params={"team_id": team.id, "role": "manager"})
    assert [u["id"] for u in resp.json()["items"]] == [manager.id]

    resp = await client.get("/api/admin/users", params={"team_id": team.id, "is_active": "false"})
    assert [u["id"] for u in resp.json()["items"]] == [gone.id]

    resp = await client.get("/api/admin/users", params={"role": "admin"})
    ids = [u["id"] for u in resp.json()["items"]]
    assert admin.id in ids
    assert dev.id not in ids
    assert all(u["team"] is None for u in resp.json()["items"])

    resp = await client.get("/api/admin/users", params={"limit": 1, "offset": 1})
    assert resp.json()["limit"] == 1
    assert len(resp.json()["items"]) == 1

    assert (await client.get("/api/admin/users", params={"role": "boss"})).status_code == 422


async def test_change_role_and_team(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team_a = await make_team(db)
    team_b = await make_team(db)
    user = await make_user(db, team=team_a)

    resp = await client.patch(
        f"/api/admin/users/{user.id}", json={"role": "manager", "team_id": team_b.id}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "manager"
    assert resp.json()["team"]["id"] == team_b.id

    # Role only: team kept.
    resp = await client.patch(f"/api/admin/users/{user.id}", json={"role": "dev"})
    assert resp.json()["team"]["id"] == team_b.id

    # Promote to admin: team cleared.
    resp = await client.patch(f"/api/admin/users/{user.id}", json={"role": "admin"})
    assert resp.status_code == 200
    assert resp.json()["team"] is None

    # Admins cannot have a team.
    resp = await client.patch(f"/api/admin/users/{user.id}", json={"team_id": team_a.id})
    assert resp.status_code == 422
    assert "team_id" in resp.json()["error"]["fields"]

    # Demoting an admin requires a team.
    resp = await client.patch(f"/api/admin/users/{user.id}", json={"role": "dev"})
    assert resp.status_code == 422
    assert "team_id" in resp.json()["error"]["fields"]
    resp = await client.patch(
        f"/api/admin/users/{user.id}", json={"role": "dev", "team_id": team_a.id}
    )
    assert resp.status_code == 200
    assert resp.json()["team"]["id"] == team_a.id


async def test_update_user_validation(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    user = await make_user(db)

    resp = await client.patch(f"/api/admin/users/{user.id}", json={"team_id": 999999})
    assert resp.status_code == 422
    resp = await client.patch(f"/api/admin/users/{user.id}", json={"team_id": None})
    assert resp.status_code == 422
    resp = await client.patch(f"/api/admin/users/{user.id}", json={"role": "boss"})
    assert resp.status_code == 422
    resp = await client.patch("/api/admin/users/999999", json={"role": "dev"})
    assert resp.status_code == 404


async def test_admin_cannot_demote_self(client: AsyncClient, db: AsyncSession) -> None:
    admin = await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)

    for role in ("manager", "dev"):
        resp = await client.patch(
            f"/api/admin/users/{admin.id}", json={"role": role, "team_id": team.id}
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "self_demotion"

    # A no-op update of yourself is allowed.
    resp = await client.patch(f"/api/admin/users/{admin.id}", json={"role": "admin"})
    assert resp.status_code == 200
    await db.refresh(admin)
    assert admin.role == Role.ADMIN


async def test_admin_cannot_deactivate_self(client: AsyncClient, db: AsyncSession) -> None:
    admin = await login_as(client, db, role=Role.ADMIN)
    resp = await client.post(f"/api/admin/users/{admin.id}/deactivate")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "self_deactivation"
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_admin_can_demote_another_admin(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    other = await make_user(db, role=Role.ADMIN)
    team = await make_team(db)
    resp = await client.patch(
        f"/api/admin/users/{other.id}", json={"role": "manager", "team_id": team.id}
    )
    assert resp.status_code == 200


async def test_deactivate_revokes_sessions_and_blocks_login(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    from httpx import ASGITransport

    target = await make_user(db, password=PASSWORD)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as theirs:
        assert (await login(theirs, target.username)).status_code == 200
        assert (await theirs.get("/api/auth/me")).status_code == 200

        await login_as(client, db, role=Role.ADMIN)
        resp = await client.post(f"/api/admin/users/{target.id}/deactivate")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        assert (await theirs.get("/api/auth/me")).status_code == 401
        live = await db.scalars(
            select(UserSession).where(
                UserSession.user_id == target.id, UserSession.revoked_at.is_(None)
            )
        )
        assert live.all() == []
        assert (await login(theirs, target.username)).status_code == 401

        resp = await client.post(f"/api/admin/users/{target.id}/activate")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True
        assert (await login(theirs, target.username)).status_code == 200


async def test_deactivate_unknown_user(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    assert (await client.post("/api/admin/users/999999/deactivate")).status_code == 404
    assert (await client.post("/api/admin/users/999999/activate")).status_code == 404


# ---------------------------------------------------------------- invite links


async def test_regenerate_invite_link(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    created = (
        await client.post(
            "/api/admin/invites",
            json={"email": "re@example.com", "role": "dev", "team_id": team.id},
        )
    ).json()
    old_token = created["invite_url"].rsplit("/", 1)[1]

    resp = await client.post(f"/api/admin/invites/{created['id']}/link")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    new_token = body["invite_url"].rsplit("/", 1)[1]
    assert new_token != old_token
    assert body["expires_at"] == created["expires_at"]

    assert (await client.get(f"/api/invites/{old_token}")).status_code == 404
    assert (await client.get(f"/api/invites/{new_token}")).status_code == 200


async def test_regenerate_link_only_for_pending(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    created = (
        await client.post(
            "/api/admin/invites",
            json={"email": "acc@example.com", "role": "dev", "team_id": team.id},
        )
    ).json()
    invite = await db.get(Invite, created["id"])
    assert invite is not None
    invite.accepted_at = invite.created_at
    await db.flush()

    resp = await client.post(f"/api/admin/invites/{created['id']}/link")
    assert resp.status_code == 409
    assert (await client.post("/api/admin/invites/999999/link")).status_code == 404


async def test_user_model_untouched_on_failed_update(client: AsyncClient, db: AsyncSession) -> None:
    admin_id = (await login_as(client, db, role=Role.ADMIN)).id
    team = await make_team(db)
    resp = await client.patch(
        f"/api/admin/users/{admin_id}", json={"role": "dev", "team_id": team.id}
    )
    assert resp.status_code == 409
    db.expire_all()
    fresh = await db.scalar(select(User).where(User.id == admin_id))
    assert fresh is not None
    assert fresh.role == Role.ADMIN
    assert fresh.team_id is None
