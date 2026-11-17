"""Personal dashboard: aggregation numbers, week boundaries, time zone handling, and
that nobody ever receives another user's numbers."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import ProcessRun, Role, RunStatus, User
from tests.auth_helpers import login_as
from tests.factories import (
    make_category,
    make_log,
    make_project,
    make_status,
    make_task,
    make_user,
)
from tests.test_processes import _defaults

pytestmark = pytest.mark.anyio

# 2026-03-08 is a Sunday; 2026-03-09 a Monday.
SUNDAY = date(2026, 3, 8)
MONDAY = date(2026, 3, 9)


def _today() -> date:
    return datetime.now(get_settings().tz).date()


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


async def _get(client: AsyncClient, path: str, **params: object) -> dict:
    resp = await client.get(f"/api/dashboard/{path}", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _log(db: AsyncSession, user: User, day: date, hours: str, **kw: object) -> None:
    await make_log(db, user=user, log_date=day, hours_spent=Decimal(hours), **kw)


# ---------------------------------------------------------------- access


async def test_endpoints_require_login(client: AsyncClient) -> None:
    rng = {"date_from": "2026-03-01", "date_to": "2026-03-31"}
    assert (await client.get("/api/dashboard/hours/daily")).status_code == 401
    assert (await client.get("/api/dashboard/hours/weekly")).status_code == 401
    assert (await client.get("/api/dashboard/hours/by-project", params=rng)).status_code == 401
    assert (await client.get("/api/dashboard/hours/by-category", params=rng)).status_code == 401
    assert (await client.get("/api/dashboard/tasks", params=rng)).status_code == 401
    assert (await client.get("/api/runs")).status_code == 401


async def test_range_is_validated(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    resp = await client.get(
        "/api/dashboard/hours/by-project",
        params={"date_from": "2026-03-10", "date_to": "2026-03-01"},
    )
    assert resp.status_code == 422
    resp = await client.get("/api/dashboard/tasks", params={"date_from": "2026-03-10"})
    assert resp.status_code == 422
    assert "date_to" in resp.json()["error"]["fields"]


# ---------------------------------------------------------------- hours over time


async def test_hours_per_day_covers_one_monday_to_sunday_week(
    client: AsyncClient, db: AsyncSession
) -> None:
    me = await login_as(client, db)
    await _log(db, me, SUNDAY, "5")  # previous week
    await _log(db, me, MONDAY, "2.5")
    await _log(db, me, MONDAY, "1.25")
    await _log(db, me, MONDAY + timedelta(days=6), "3")  # Sunday, same week
    await _log(db, me, MONDAY + timedelta(days=7), "4")  # next Monday

    body = await _get(client, "hours/daily", week="2026-03-11")  # a Wednesday
    assert body["week_start"] == "2026-03-09"
    assert body["week_end"] == "2026-03-15"
    assert [d["date"] for d in body["days"]] == [
        (MONDAY + timedelta(days=i)).isoformat() for i in range(7)
    ]
    assert [d["hours"] for d in body["days"]] == [3.75, 0, 0, 0, 0, 0, 3]
    assert body["total"] == 6.75

    previous = await _get(client, "hours/daily", week=SUNDAY.isoformat())
    assert previous["week_start"] == "2026-03-02"
    assert previous["days"][-1] == {"date": "2026-03-08", "hours": 5}
    assert previous["total"] == 5


async def test_hours_per_day_defaults_to_current_week(
    client: AsyncClient, db: AsyncSession
) -> None:
    me = await login_as(client, db)
    today = _today()
    await _log(db, me, today, "2")
    body = await _get(client, "hours/daily")
    assert body["week_start"] == _monday(today).isoformat()
    assert body["total"] == 2


async def test_hours_per_week_last_eight_weeks(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    this_monday = _monday(_today())
    first_monday = this_monday - timedelta(weeks=7)
    await _log(db, me, this_monday, "1")
    await _log(db, me, this_monday + timedelta(days=6), "2")  # this Sunday
    await _log(db, me, this_monday - timedelta(days=1), "4")  # last Sunday
    await _log(db, me, first_monday, "8")  # oldest week shown
    await _log(db, me, first_monday - timedelta(days=1), "16")  # just outside

    weeks = (await _get(client, "hours/weekly"))["weeks"]
    assert len(weeks) == 8
    assert weeks[0] == {"week_start": first_monday.isoformat(), "hours": 8}
    assert weeks[-1] == {"week_start": this_monday.isoformat(), "hours": 3}
    assert weeks[-2] == {"week_start": (this_monday - timedelta(weeks=1)).isoformat(), "hours": 4}
    assert sum(w["hours"] for w in weeks) == 15


# ---------------------------------------------------------------- hours by dimension


async def test_hours_by_project_and_category(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    alpha, beta = await make_project(db), await make_project(db, is_active=False)
    code, review = await make_category(db, color="#112233"), await make_category(db)
    await _log(db, me, MONDAY, "3", project_id=alpha.id, category_id=code.id)
    await _log(db, me, MONDAY, "2", project_id=beta.id, category_id=review.id)
    await _log(db, me, MONDAY + timedelta(days=1), "1.5", category_id=code.id)
    await _log(db, me, MONDAY + timedelta(days=1), "4", project_id=alpha.id, category_id=review.id)
    await _log(db, me, MONDAY + timedelta(days=30), "9", project_id=beta.id, category_id=code.id)

    rng = {"date_from": "2026-03-09", "date_to": "2026-03-15"}
    projects = await _get(client, "hours/by-project", **rng)
    assert projects["total"] == 10.5
    assert [(i["project"] and i["project"]["id"], i["hours"]) for i in projects["items"]] == [
        (alpha.id, 7),
        (beta.id, 2),
        (None, 1.5),
    ]
    # Inactive values still show, flagged as inactive.
    assert projects["items"][1]["project"]["is_active"] is False

    categories = await _get(client, "hours/by-category", **rng)
    assert categories["total"] == 10.5
    assert [(i["category"]["id"], i["hours"]) for i in categories["items"]] == [
        (review.id, 6),
        (code.id, 4.5),
    ]
    assert categories["items"][1]["category"]["color"] == "#112233"

    empty = await _get(client, "hours/by-project", date_from="2020-01-01", date_to="2020-01-31")
    assert empty["items"] == []
    assert empty["total"] == 0


# ---------------------------------------------------------------- tasks


async def test_task_counts(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    done = await make_status(db, is_done=True)
    todo = await make_status(db)
    today = _today()

    def at(day: date) -> datetime:
        return datetime(day.year, day.month, day.day, 12, tzinfo=UTC)

    await make_task(db, user=me, status_id=done.id, completed_at=at(MONDAY))
    await make_task(db, user=me, status_id=done.id, completed_at=at(MONDAY + timedelta(days=6)))
    await make_task(db, user=me, status_id=done.id, completed_at=at(SUNDAY))  # before range
    # Done but overdue-looking: never counted as overdue.
    await make_task(
        db, user=me, status_id=done.id, completed_at=at(SUNDAY), due_date=today - timedelta(days=9)
    )
    await make_task(db, user=me, status_id=todo.id)
    await make_task(db, user=me, status_id=todo.id, due_date=today - timedelta(days=1))
    await make_task(db, user=me, status_id=todo.id, due_date=today)  # due today: not overdue

    body = await _get(client, "tasks", date_from="2026-03-09", date_to="2026-03-15")
    assert (body["completed"], body["open"], body["overdue"]) == (2, 3, 1)


async def test_completion_date_follows_app_timezone(
    client: AsyncClient, db: AsyncSession, settings_override
) -> None:
    settings_override(app_timezone="Asia/Manila")  # UTC+8
    me = await login_as(client, db)
    done = await make_status(db, is_done=True)
    # 20:00 UTC on Sunday is 04:00 Monday in Manila.
    await make_task(
        db, user=me, status_id=done.id, completed_at=datetime(2026, 3, 8, 20, tzinfo=UTC)
    )

    sunday = await _get(client, "tasks", date_from="2026-03-08", date_to="2026-03-08")
    monday = await _get(client, "tasks", date_from="2026-03-09", date_to="2026-03-09")
    assert (sunday["completed"], monday["completed"]) == (0, 1)


# ---------------------------------------------------------------- isolation


@pytest.mark.parametrize("role", [Role.ADMIN, Role.MANAGER, Role.DEV])
async def test_never_includes_other_users_numbers(
    client: AsyncClient, db: AsyncSession, role: Role
) -> None:
    me = await login_as(client, db, role=role)
    # A teammate (same team as a manager/dev) with plenty of data.
    other = await make_user(db, team_id=me.team_id) if me.team_id else await make_user(db)
    done = await make_status(db, is_done=True)
    project, category = await make_project(db), await make_category(db)
    today = _today()
    for day in (MONDAY, today):
        await _log(db, other, day, "7", project_id=project.id, category_id=category.id)
    await make_task(db, user=other, status_id=done.id, completed_at=datetime.now(UTC))
    await make_task(db, user=other, due_date=today - timedelta(days=3))

    await _log(db, me, MONDAY, "1", project_id=project.id, category_id=category.id)

    assert (await _get(client, "hours/daily", week="2026-03-09"))["total"] == 1
    assert sum(w["hours"] for w in (await _get(client, "hours/weekly"))["weeks"]) == 0
    wide = {"date_from": "2026-01-01", "date_to": today.isoformat()}
    projects = await _get(client, "hours/by-project", **wide)
    assert [(i["project"]["id"], i["hours"]) for i in projects["items"]] == [(project.id, 1)]
    categories = await _get(client, "hours/by-category", **wide)
    assert [(i["category"]["id"], i["hours"]) for i in categories["items"]] == [(category.id, 1)]
    counts = await _get(client, "tasks", **wide)
    assert (counts["completed"], counts["open"], counts["overdue"]) == (0, 0, 0)


# ---------------------------------------------------------------- runs


async def test_runs_list_is_own_only_and_filters_by_status(
    client: AsyncClient, new_client, db: AsyncSession
) -> None:
    await _defaults(db)
    done = await make_status(db, is_done=True)
    me = await login_as(client, db)
    other_client = new_client()
    await login_as(other_client, db)

    async def start(c: AsyncClient, name: str, steps: int) -> dict:
        resp = await c.post(
            "/api/processes",
            json={"name": name, "steps": [{"title": f"S{i}"} for i in range(steps)]},
        )
        assert resp.status_code == 201, resp.text
        resp = await c.post(f"/api/processes/{resp.json()['id']}/runs", json={})
        assert resp.status_code == 201, resp.text
        return resp.json()

    first = await start(client, "First", 2)
    second = await start(client, "Second", 3)
    await start(other_client, "Theirs", 1)
    # Finish one task of the second run, and complete the first run entirely.
    await client.patch(f"/api/tasks/{second['tasks'][0]['id']}", json={"status_id": done.id})
    for task in first["tasks"]:
        await client.patch(f"/api/tasks/{task['id']}", json={"status_id": done.id})

    resp = await client.get("/api/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert {r["id"] for r in body["items"]} == {first["id"], second["id"]}

    resp = await client.get("/api/runs", params={"status": "in_progress"})
    items = resp.json()["items"]
    assert [r["id"] for r in items] == [second["id"]]
    assert items[0]["process"]["name"] == "Second"
    assert items[0]["progress"] == {"done": 1, "total": 3}

    run = await db.get_one(ProcessRun, first["id"], populate_existing=True)
    assert run.status == RunStatus.COMPLETED
    assert me.id == run.user_id
