"""Prod logs and team logs: ownership, team snapshot, audit, 24-hour caps, team access.

Linked-dropdown rules and planned/actual fields are in test_prod_log_fields.py."""

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProdLog, Role, Team, User
from tests.auth_helpers import login_as, use_new_session
from tests.factories import (
    make_category,
    make_linked,
    make_log,
    make_project,
    make_team,
    make_user,
)

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _daily_cap(settings_override: Callable[..., object]) -> None:
    """Daily totals are capped at WORKDAY_HOURS; pin it so the numbers below hold."""
    settings_override(workday_hours=Decimal(9))


TODAY = date.today()


async def _body(db: AsyncSession, **kw: object) -> dict[str, object]:
    refs = await make_linked(db)
    return {
        "log_date": TODAY.isoformat(),
        "description": "Worked",
        "hours_spent": 2,
        **refs.ids(),
        **kw,
    }


# ---------------------------------------------------------------- own logs


async def test_endpoints_require_login(client: AsyncClient) -> None:
    assert (await client.get("/api/logs")).status_code == 401
    assert (await client.get("/api/teams/1/logs")).status_code == 401
    assert (await client.get("/api/teams/1/members")).status_code == 401


async def test_create_sets_team_snapshot_and_updated_by(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await login_as(client, db)
    resp = await client.post("/api/logs", json=await _body(db, hours_spent="1.25"))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["hours_spent"] == 1.25
    assert body["team_id"] == user.team_id
    assert body["user"] == {"id": user.id, "username": user.username}
    assert body["updated_by"]["id"] == user.id

    log = await db.get(ProdLog, body["id"])
    assert log is not None
    assert (log.team_id, log.updated_by, log.user_id) == (user.team_id, user.id, user.id)


async def test_admin_log_has_no_team(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    resp = await client.post("/api/logs", json=await _body(db))
    assert resp.status_code == 201
    assert resp.json()["team_id"] is None


@pytest.mark.parametrize("role", [Role.MANAGER, Role.DEV])
async def test_cannot_touch_another_users_log(
    client: AsyncClient, db: AsyncSession, role: Role
) -> None:
    """Outside your team (or as a dev in the same team) another user's log is 404."""
    me = await login_as(client, db, role=role)
    other = await make_user(db, team_id=me.team_id) if role == Role.DEV else await make_user(db)
    log = await make_log(db, user=other)

    url = f"/api/logs/{log.id}"
    assert (await client.get(url)).status_code == 404
    assert (await client.patch(url, json={"description": "Mine"})).status_code == 404
    assert (await client.delete(url)).status_code == 404
    listed = (await client.get("/api/logs")).json()
    assert log.id not in [item["id"] for item in listed["items"]]


async def test_own_list_excludes_others_even_for_admin(
    client: AsyncClient, db: AsyncSession
) -> None:
    me = await login_as(client, db, role=Role.ADMIN)
    mine = await make_log(db, user=me)
    await make_log(db)
    items = (await client.get("/api/logs")).json()["items"]
    assert [item["id"] for item in items] == [mine.id]


async def test_update_and_delete_own(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    log = await make_log(db, user=me, description="old")
    resp = await client.patch(f"/api/logs/{log.id}", json={"description": "", "hours_spent": 3.5})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["description"], body["hours_spent"]) == (None, 3.5)

    assert (await client.delete(f"/api/logs/{log.id}")).status_code == 204
    assert await db.get(ProdLog, log.id) is None


async def test_validation(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    for hours in (0, -1, 24.5, "1.234"):
        resp = await client.post("/api/logs", json=await _body(db, hours_spent=hours))
        assert resp.status_code == 422, hours
        assert "hours_spent" in resp.json()["error"]["fields"]
    resp = await client.post("/api/logs", json=await _body(db, title="Old note field"))
    assert resp.status_code == 201  # unknown fields are ignored; there is no note any more
    assert "title" not in resp.json()
    log = await make_log(db)
    resp = await client.patch(f"/api/logs/{log.id}", json={"category_id": None})
    assert resp.status_code == 422


# ---------------------------------------------------------------- references


async def test_category_and_project_required(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    refs = await make_linked(db)
    body = {
        "log_date": TODAY.isoformat(),
        "hours_spent": 1,
        "project_id": refs.project.id,
        "activity_id": refs.activity.id,
    }
    resp = await client.post("/api/logs", json=body)
    assert resp.status_code == 422
    assert "category_id" in resp.json()["error"]["fields"]
    resp = await client.post(
        "/api/logs", json={**body, "category_id": refs.category.id, "project_id": None}
    )
    assert resp.status_code == 422
    assert "project_id" in resp.json()["error"]["fields"]


async def test_inactive_values_rejected_on_create_kept_on_update(
    client: AsyncClient, db: AsyncSession
) -> None:
    me = await login_as(client, db)
    inactive_cat = await make_category(db, is_active=False)
    inactive_proj = await make_project(db, is_active=False)
    resp = await client.post("/api/logs", json=await _body(db, category_id=inactive_cat.id))
    assert resp.status_code == 422
    resp = await client.post("/api/logs", json=await _body(db, project_id=inactive_proj.id))
    assert resp.status_code == 422

    log = await make_log(db, user=me, category_id=inactive_cat.id, project_id=inactive_proj.id)
    resp = await client.patch(
        f"/api/logs/{log.id}",
        json={
            "description": "Edited",
            "category_id": inactive_cat.id,
            "project_id": inactive_proj.id,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["category"]["is_active"] is False

    other_inactive = await make_category(db, is_active=False)
    resp = await client.patch(f"/api/logs/{log.id}", json={"category_id": other_inactive.id})
    assert resp.status_code == 422


# ---------------------------------------------------------------- 24-hour cap


async def test_daily_cap_on_create(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    await make_log(db, user=me, hours_spent=Decimal("5"))
    await make_log(db, user=me, log_date=TODAY - timedelta(days=1), hours_spent=Decimal("5"))

    resp = await client.post("/api/logs", json=await _body(db, hours_spent=4.01))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "daily_hours_exceeded"
    assert "hours_spent" in resp.json()["error"]["fields"]

    # Exactly the cap (WORKDAY_HOURS) is allowed.
    assert (await client.post("/api/logs", json=await _body(db, hours_spent=4))).status_code == 201
    # Someone else's hours on the same day don't count.
    await make_log(db, hours_spent=Decimal("9"))


async def test_daily_cap_on_update(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    await make_log(db, user=me, hours_spent=Decimal("5"))
    log = await make_log(db, user=me, hours_spent=Decimal("4"))
    elsewhere = await make_log(
        db, user=me, log_date=TODAY - timedelta(days=1), hours_spent=Decimal("5")
    )

    # Its own previous hours are not double-counted.
    assert (await client.patch(f"/api/logs/{log.id}", json={"description": "x"})).status_code == 200
    resp = await client.patch(f"/api/logs/{log.id}", json={"hours_spent": 4.5})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "daily_hours_exceeded"
    # Moving another day's log onto the full day is rejected too.
    resp = await client.patch(f"/api/logs/{elsewhere.id}", json={"log_date": TODAY.isoformat()})
    assert resp.status_code == 422


async def test_daily_cap_applies_to_author_on_admin_edit(
    client: AsyncClient, db: AsyncSession
) -> None:
    author = await make_user(db)
    await make_log(db, user=author, hours_spent=Decimal("23"))
    log = await make_log(db, user=author, hours_spent=Decimal("1"))
    await login_as(client, db, role=Role.ADMIN)
    resp = await client.patch(f"/api/logs/{log.id}", json={"hours_spent": 2})
    assert resp.status_code == 422


# ---------------------------------------------------------------- admin and manager


async def test_admin_edit_sets_updated_by(client: AsyncClient, db: AsyncSession) -> None:
    author = await make_user(db)
    log = await make_log(db, user=author)
    admin = await login_as(client, db, role=Role.ADMIN)

    resp = await client.patch(f"/api/logs/{log.id}", json={"description": "Fixed by admin"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated_by"] == {"id": admin.id, "username": admin.username}
    assert body["user"]["id"] == author.id
    assert body["team_id"] == author.team_id

    await db.refresh(log)
    assert (log.updated_by, log.user_id, log.team_id) == (admin.id, author.id, author.team_id)

    assert (await client.delete(f"/api/logs/{log.id}")).status_code == 204


async def test_manager_can_read_but_not_write_team_log(
    client: AsyncClient, db: AsyncSession
) -> None:
    manager = await login_as(client, db, role=Role.MANAGER)
    member = await make_user(db, team_id=manager.team_id)
    log = await make_log(db, user=member)

    url = f"/api/logs/{log.id}"
    assert (await client.get(url)).status_code == 200
    resp = await client.patch(url, json={"description": "Manager edit"})
    assert resp.status_code == 403
    assert (await client.delete(url)).status_code == 403
    await db.refresh(log)
    assert log.description != "Manager edit"
    assert log.updated_by == member.id


# ---------------------------------------------------------------- team endpoints


async def test_dev_cannot_access_team_endpoints(client: AsyncClient, db: AsyncSession) -> None:
    dev = await login_as(client, db)
    for team_id in (dev.team_id, (await make_team(db)).id):
        assert (await client.get(f"/api/teams/{team_id}/logs")).status_code == 403
        assert (await client.get(f"/api/teams/{team_id}/members")).status_code == 403


async def test_manager_cannot_access_another_team(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.MANAGER)
    other_team = await make_team(db)
    await make_log(db, user=await make_user(db, team=other_team))
    assert (await client.get(f"/api/teams/{other_team.id}/logs")).status_code == 404
    assert (await client.get(f"/api/teams/{other_team.id}/members")).status_code == 404


async def test_manager_sees_own_team_logs(client: AsyncClient, db: AsyncSession) -> None:
    manager = await login_as(client, db, role=Role.MANAGER)
    member = await make_user(db, team_id=manager.team_id)
    mine = await make_log(db, user=manager)
    theirs = await make_log(db, user=member)
    await make_log(db)  # another team

    resp = await client.get(f"/api/teams/{manager.team_id}/logs")
    assert resp.status_code == 200
    assert {item["id"] for item in resp.json()["items"]} == {mine.id, theirs.id}

    resp = await client.get(f"/api/teams/{manager.team_id}/logs", params={"user_id": member.id})
    assert [item["id"] for item in resp.json()["items"]] == [theirs.id]


async def test_admin_any_team_and_missing_team(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    log = await make_log(db)
    resp = await client.get(f"/api/teams/{log.team_id}/logs")
    assert [item["id"] for item in resp.json()["items"]] == [log.id]
    assert (await client.get("/api/teams/999999/logs")).status_code == 404


async def test_team_change_keeps_logs_with_old_team(client: AsyncClient, db: AsyncSession) -> None:
    old_team, new_team = await make_team(db), await make_team(db)
    old_manager = await make_user(db, role=Role.MANAGER, team=old_team)
    new_manager = await make_user(db, role=Role.MANAGER, team=new_team)
    mover = await login_as(client, db, team=old_team)
    old_log_id = (await client.post("/api/logs", json=await _body(db))).json()["id"]

    mover.team_id = new_team.id
    await db.flush()
    new_log_id = (await client.post("/api/logs", json=await _body(db))).json()["id"]
    # Editing the old log afterwards doesn't move it either.
    assert (
        await client.patch(f"/api/logs/{old_log_id}", json={"description": "Still old"})
    ).status_code == 200

    old_log = await db.get(ProdLog, old_log_id)
    new_log = await db.get(ProdLog, new_log_id)
    assert old_log is not None
    assert new_log is not None
    await db.refresh(old_log)
    assert old_log.team_id == old_team.id
    assert new_log.team_id == new_team.id

    async def team_log_ids(manager: User, team: Team) -> set[int]:
        await login_as_existing(client, db, manager)
        resp = await client.get(f"/api/teams/{team.id}/logs")
        assert resp.status_code == 200
        return {item["id"] for item in resp.json()["items"]}

    assert await team_log_ids(old_manager, old_team) == {old_log_id}
    assert await team_log_ids(new_manager, new_team) == {new_log_id}

    # The old team's manager can still open the old log, the new manager cannot.
    await login_as_existing(client, db, old_manager)
    assert (await client.get(f"/api/logs/{old_log_id}")).status_code == 200
    assert (await client.get(f"/api/logs/{new_log_id}")).status_code == 404
    await login_as_existing(client, db, new_manager)
    assert (await client.get(f"/api/logs/{old_log_id}")).status_code == 404

    # The mover still shows up as a (former) member of the old team.
    await login_as_existing(client, db, old_manager)
    members = (await client.get(f"/api/teams/{old_team.id}/members")).json()["items"]
    by_id = {m["id"]: m for m in members}
    assert by_id[mover.id]["is_current_member"] is False
    assert by_id[old_manager.id]["is_current_member"] is True


async def login_as_existing(client: AsyncClient, db: AsyncSession, user: User) -> None:
    client.cookies.clear()
    await use_new_session(client, db, user)


# ---------------------------------------------------------------- lists


async def test_filters_and_day_totals(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    yesterday = TODAY - timedelta(days=1)
    project = await make_project(db)
    category = await make_category(db)
    a = await make_log(db, user=me, hours_spent=Decimal("2"), project_id=project.id)
    b = await make_log(db, user=me, hours_spent=Decimal("1.5"), category_id=category.id)
    c = await make_log(db, user=me, log_date=yesterday, hours_spent=Decimal("3"))

    items = (await client.get("/api/logs")).json()["items"]
    assert [i["id"] for i in items] == [b.id, a.id, c.id]  # newest date, newest first
    assert [i["day_total_hours"] for i in items] == [3.5, 3.5, 3.0]

    async def ids(**params: object) -> list[int]:
        resp = await client.get("/api/logs", params=params)
        assert resp.status_code == 200, resp.text
        return [i["id"] for i in resp.json()["items"]]

    assert await ids(date_from=TODAY.isoformat()) == [b.id, a.id]
    assert await ids(date_to=yesterday.isoformat()) == [c.id]
    assert await ids(project_id=project.id) == [a.id]
    assert await ids(category_id=category.id) == [b.id]

    # Day totals cover the filtered logs on every page, not just this page.
    page = (await client.get("/api/logs", params={"limit": 1})).json()
    assert page["total"] == 3
    assert page["items"][0]["day_total_hours"] == 3.5

    bad = await client.get(
        "/api/logs", params={"date_from": TODAY.isoformat(), "date_to": yesterday.isoformat()}
    )
    assert bad.status_code == 422
