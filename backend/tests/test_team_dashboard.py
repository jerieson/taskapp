"""Team dashboard and admin overview: access rules, numbers per team and member, the
team snapshot on prod logs, and that task contents never leak into team responses."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.base import utcnow
from app.models import AIFeature, AIRequest, Invite, Role, User
from tests.auth_helpers import login_as
from tests.factories import (
    make_category,
    make_log,
    make_project,
    make_status,
    make_task,
    make_team,
    make_user,
)

pytestmark = pytest.mark.anyio

MONDAY = date(2026, 3, 9)
RANGE = {"date_from": "2026-03-09", "date_to": "2026-03-15"}
ENDPOINTS = [
    ("hours/daily", {"week": "2026-03-09"}),
    ("hours/weekly", {}),
    ("hours/by-member", RANGE),
    ("hours/by-project", RANGE),
    ("hours/by-category", RANGE),
    ("tasks", RANGE),
]


def _today() -> date:
    return datetime.now(get_settings().tz).date()


async def _get(client: AsyncClient, team_id: int, path: str, **params: object) -> dict:
    resp = await client.get(f"/api/teams/{team_id}/dashboard/{path}", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _log(db: AsyncSession, user: User, day: date, hours: str, **kw: object) -> None:
    await make_log(db, user=user, log_date=day, hours_spent=Decimal(hours), **kw)


def _member_hours(items: list[dict]) -> dict[int, float]:
    return {item["member"]["id"]: item["hours"] for item in items}


# ---------------------------------------------------------------- access


async def test_requires_login(client: AsyncClient) -> None:
    for path, params in ENDPOINTS:
        resp = await client.get(f"/api/teams/1/dashboard/{path}", params=params)
        assert resp.status_code == 401, path


async def test_dev_is_forbidden(client: AsyncClient, db: AsyncSession) -> None:
    dev = await login_as(client, db)
    for team_id in (dev.team_id, (await make_team(db)).id):
        for path, params in ENDPOINTS:
            resp = await client.get(f"/api/teams/{team_id}/dashboard/{path}", params=params)
            assert resp.status_code == 403, path


async def test_manager_other_team_is_not_found(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.MANAGER)
    other = await make_team(db)
    await _log(db, await make_user(db, team=other), MONDAY, "3")
    for path, params in ENDPOINTS:
        resp = await client.get(f"/api/teams/{other.id}/dashboard/{path}", params=params)
        assert resp.status_code == 404, path


async def test_admin_any_team_and_missing_team(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    team = await make_team(db)
    await _log(db, await make_user(db, team=team), MONDAY, "3")
    assert (await _get(client, team.id, "hours/daily", week="2026-03-09"))["total"] == 3
    for path, params in ENDPOINTS:
        resp = await client.get(f"/api/teams/999999/dashboard/{path}", params=params)
        assert resp.status_code == 404, path


# ---------------------------------------------------------------- numbers


async def test_hours_for_team_and_members(client: AsyncClient, db: AsyncSession) -> None:
    manager = await login_as(client, db, role=Role.MANAGER)
    team_id = manager.team_id
    assert team_id is not None
    ann = await make_user(db, team_id=team_id, username="ann")
    bob = await make_user(db, team_id=team_id, username="bob")
    idle = await make_user(db, team_id=team_id, username="cat")  # no logs: listed with 0
    await make_user(db, team_id=team_id, username="gone", is_active=False)  # hidden
    outsider = await make_user(db)
    project, category = await make_project(db), await make_category(db)

    sunday = MONDAY - timedelta(days=1)
    await _log(db, ann, MONDAY, "3", project_id=project.id, category_id=category.id)
    await _log(db, ann, MONDAY + timedelta(days=6), "1.5", category_id=category.id)
    await _log(db, bob, MONDAY + timedelta(days=2), "4", project_id=project.id)
    await _log(db, bob, sunday, "8")  # previous week
    await _log(db, outsider, MONDAY, "9")  # another team

    daily = await _get(client, team_id, "hours/daily", week="2026-03-11")
    assert daily["week_start"] == "2026-03-09"
    assert daily["total"] == 8.5
    assert [d["hours"] for d in daily["days"]] == [3, 0, 4, 0, 0, 0, 1.5]
    by_name = {m["member"]["username"]: m for m in daily["members"]}
    # Active current members (with or without hours) by username; "gone" is inactive.
    assert list(by_name) == ["ann", "bob", "cat", manager.username]
    assert by_name["ann"]["total"] == 4.5
    assert [d["hours"] for d in by_name["bob"]["days"]] == [0, 0, 4, 0, 0, 0, 0]
    assert by_name["cat"]["total"] == 0

    members = await _get(client, team_id, "hours/by-member", **RANGE)
    assert members["total"] == 8.5
    assert [(i["member"]["id"], i["hours"]) for i in members["items"][:2]] == [
        (ann.id, 4.5),
        (bob.id, 4),
    ]
    assert _member_hours(members["items"])[idle.id] == 0

    projects = await _get(client, team_id, "hours/by-project", **RANGE)
    assert [(i["project"] and i["project"]["id"], i["hours"]) for i in projects["items"]] == [
        (project.id, 7),
        (None, 1.5),
    ]
    categories = await _get(client, team_id, "hours/by-category", **RANGE)
    assert categories["total"] == 8.5
    activities = await _get(client, team_id, "hours/by-activity", **RANGE)
    assert activities["total"] == 8.5
    assert len(activities["items"]) == 3  # one new activity per row in range (factory)


async def test_rows_without_actual_hours_are_ignored(client: AsyncClient, db: AsyncSession) -> None:
    manager = await login_as(client, db, role=Role.MANAGER)
    team_id = manager.team_id
    assert team_id is not None
    planner = await make_user(db, team_id=team_id, is_active=False)  # listed only with hours
    await make_log(db, user=planner, log_date=MONDAY, hours_spent=None, planned_hours=Decimal(8))
    await _log(db, manager, MONDAY, "2")

    daily = await _get(client, team_id, "hours/daily", week=MONDAY.isoformat())
    assert daily["total"] == 2
    assert planner.id not in [m["member"]["id"] for m in daily["members"]]
    for path in ("by-member", "by-project", "by-category", "by-activity"):
        body = await _get(client, team_id, f"hours/{path}", **RANGE)
        assert body["total"] == 2, path
    members = await _get(client, team_id, "hours/by-member", **RANGE)
    assert planner.id not in _member_hours(members["items"])


async def test_hours_per_week(client: AsyncClient, db: AsyncSession) -> None:
    manager = await login_as(client, db, role=Role.MANAGER)
    team_id = manager.team_id
    assert team_id is not None
    ann = await make_user(db, team_id=team_id)
    this_monday = _today() - timedelta(days=_today().weekday())
    await _log(db, ann, this_monday, "2")
    await _log(db, ann, this_monday - timedelta(days=1), "3")  # last week's Sunday
    await _log(db, manager, this_monday - timedelta(weeks=7), "1")  # oldest week shown
    await _log(db, manager, this_monday - timedelta(weeks=8), "5")  # too old

    weekly = await _get(client, team_id, "hours/weekly")
    assert len(weekly["weeks"]) == 8
    assert [w["hours"] for w in weekly["weeks"]] == [1, 0, 0, 0, 0, 0, 3, 2]
    by_id = {m["member"]["id"]: m for m in weekly["members"]}
    assert [w["hours"] for w in by_id[ann.id]["weeks"]][-2:] == [3, 2]
    assert by_id[manager.id]["total"] == 1


async def test_task_counts_per_current_member(client: AsyncClient, db: AsyncSession) -> None:
    manager = await login_as(client, db, role=Role.MANAGER)
    team_id = manager.team_id
    ann = await make_user(db, team_id=team_id)
    done, todo = await make_status(db, is_done=True), await make_status(db)
    noon = datetime(2026, 3, 10, 12, tzinfo=UTC)
    await make_task(db, user=ann, status_id=done.id, completed_at=noon)
    await make_task(db, user=ann, status_id=todo.id, due_date=_today() - timedelta(days=1))
    await make_task(db, user=ann, status_id=todo.id)
    await make_task(db, user=await make_user(db), status_id=todo.id)  # another team

    body = await _get(client, team_id, "tasks", **RANGE)
    counts = {i["member"]["id"]: (i["completed"], i["open"], i["overdue"]) for i in body["items"]}
    assert counts == {manager.id: (0, 0, 0), ann.id: (1, 2, 1)}


async def test_numbers_follow_team_snapshot(client: AsyncClient, db: AsyncSession) -> None:
    """Hours stay with the team they were logged in; task counts follow current teams."""
    await login_as(client, db, role=Role.ADMIN)
    old_team, new_team = await make_team(db), await make_team(db)
    mover = await make_user(db, team=old_team)
    todo = await make_status(db)
    await _log(db, mover, MONDAY, "5")
    await make_task(db, user=mover, status_id=todo.id)

    mover.team_id = new_team.id
    await db.flush()
    await _log(db, mover, MONDAY + timedelta(days=1), "2")

    old = await _get(client, old_team.id, "hours/daily", week="2026-03-09")
    new = await _get(client, new_team.id, "hours/daily", week="2026-03-09")
    assert (old["total"], new["total"]) == (5, 2)
    former = old["members"][0]["member"]
    assert (former["id"], former["is_current_member"]) == (mover.id, False)

    by_member = await _get(client, old_team.id, "hours/by-member", **RANGE)
    assert _member_hours(by_member["items"]) == {mover.id: 5}

    old_tasks = await _get(client, old_team.id, "tasks", **RANGE)
    new_tasks = await _get(client, new_team.id, "tasks", **RANGE)
    assert old_tasks["items"] == []
    assert [(i["member"]["id"], i["open"]) for i in new_tasks["items"]] == [(mover.id, 1)]


async def test_no_task_contents_in_team_responses(client: AsyncClient, db: AsyncSession) -> None:
    manager = await login_as(client, db, role=Role.MANAGER)
    team_id = manager.team_id
    assert team_id is not None
    ann = await make_user(db, team_id=team_id)
    done = await make_status(db, is_done=True)
    await make_task(
        db,
        user=ann,
        title="SECRET-TASK-TITLE",
        description="SECRET-TASK-DESCRIPTION",
        status_id=done.id,
        completed_at=datetime(2026, 3, 10, 12, tzinfo=UTC),
    )
    await _log(db, ann, MONDAY, "2")

    for path, params in ENDPOINTS:
        resp = await client.get(f"/api/teams/{team_id}/dashboard/{path}", params=params)
        assert resp.status_code == 200, path
        assert "SECRET-TASK" not in resp.text, path
        assert '"task' not in resp.text, path


# ---------------------------------------------------------------- admin overview


async def test_overview_is_admin_only(client: AsyncClient, db: AsyncSession) -> None:
    assert (await client.get("/api/admin/overview")).status_code == 401
    await login_as(client, db, role=Role.MANAGER)
    assert (await client.get("/api/admin/overview")).status_code == 403
    assert (await client.get("/api/admin/ai-usage")).status_code == 403


async def test_overview_counts(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    before = (await client.get("/api/admin/overview")).json()

    team = await make_team(db)
    await make_user(db, role=Role.MANAGER, team=team)
    await make_user(db, team=team)
    await make_user(db, team=team, is_active=False)
    admin = await make_user(db, role=Role.ADMIN)
    now = utcnow()
    for expires, accepted in ((now + timedelta(days=1), None), (now - timedelta(hours=1), None)):
        db.add(
            Invite(
                email=f"x{expires.timestamp()}@example.com",
                role=Role.DEV,
                team_id=team.id,
                token_hash=f"hash-{expires.timestamp()}",
                expires_at=expires,
                accepted_at=accepted,
                created_by=admin.id,
            )
        )
    await db.flush()

    after = (await client.get("/api/admin/overview")).json()
    diff = {k: after["users"][k] - before["users"][k] for k in after["users"]}
    assert diff == {"active": 3, "inactive": 1, "admins": 1, "managers": 1, "devs": 1}
    assert after["teams"] - before["teams"] == 1
    assert after["pending_invites"] - before["pending_invites"] == 1  # expired not counted


async def test_ai_usage_last_30_days(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    assert (await client.get("/api/admin/ai-usage")).json()["items"] == []

    ann, bob = await make_user(db), await make_user(db)
    now = utcnow()

    def req(user: User, success: bool = True, days_ago: int = 0) -> AIRequest:
        return AIRequest(
            user_id=user.id,
            feature=AIFeature.DAILY_PLAN,
            provider="test",
            model="test-model",
            input_tokens=100,
            output_tokens=10,
            success=success,
            created_at=now - timedelta(days=days_ago),
        )

    db.add_all([req(ann), req(ann, success=False), req(bob), req(bob, days_ago=31)])
    await db.flush()

    body = (await client.get("/api/admin/ai-usage")).json()
    assert body["total"] == 2
    rows = [
        (r["user"]["id"], r["requests"], r["failed"], r["input_tokens"], r["output_tokens"])
        for r in body["items"]
    ]
    assert rows == [(ann.id, 2, 1, 200, 20), (bob.id, 1, 0, 100, 10)]
