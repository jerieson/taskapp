"""Weekly planning: the Friday deadline, planned/unplanned, locked planned hours and
deletes, the admin override, copying a plan, and the planning status endpoints.

The app runs in Asia/Manila (UTC+8, no DST) with the deadline at 18:30. The week under
test is Monday 2026-11-23 to Friday 2026-11-27; its deadline is Friday 2026-11-20 18:30
Manila time (10:30 UTC).
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import DeviationReason, Role
from tests.auth_helpers import login_as
from tests.factories import LinkedRefs, make_linked, make_log, make_team, make_user

pytestmark = pytest.mark.anyio

MANILA = ZoneInfo("Asia/Manila")
DEADLINE_FRIDAY = date(2026, 11, 20)
MONDAY = date(2026, 11, 23)  # the week being planned
THIS_MONDAY = date(2026, 11, 16)  # the week before (locked: it is under way)


def manila(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=MANILA)


BEFORE_DEADLINE = manila(DEADLINE_FRIDAY, 18, 29)
AT_DEADLINE = manila(DEADLINE_FRIDAY, 18, 30)
WEDNESDAY = manila(date(2026, 11, 18), 9)

SetNow = Callable[[datetime], None]


@pytest.fixture(autouse=True)
def _manila(settings_override: Callable[..., Settings]) -> None:
    settings_override(app_timezone="Asia/Manila", plan_deadline_time="18:30", workday_hours=8)


def _body(refs: LinkedRefs, day: date, **kw: object) -> dict[str, object]:
    return {"log_date": day.isoformat(), **refs.ids(), **kw}


async def _create(client: AsyncClient, body: dict[str, object]) -> dict[str, Any]:
    resp = await client.post("/api/logs", json=body)
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()
    return data


def _locked(resp: Response) -> None:
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "week_locked"


# ---------------------------------------------------------------- deadline


async def test_deadline_edges(client: AsyncClient, db: AsyncSession, set_now: SetNow) -> None:
    await login_as(client, db)
    refs = await make_linked(db)

    set_now(BEFORE_DEADLINE.astimezone(UTC))
    row = await _create(client, _body(refs, MONDAY, planned_hours=4))
    assert row["is_planned"] is True

    set_now(AT_DEADLINE)
    _locked(await client.post("/api/logs", json=_body(refs, MONDAY, planned_hours=4)))
    # Actual hours can still be logged (Planned unless the user says otherwise).
    row = await _create(client, _body(refs, MONDAY, hours_spent=2))
    assert (row["is_planned"], row["planned_hours"]) == (True, None)
    # The week after is still open.
    row = await _create(client, _body(refs, MONDAY + timedelta(days=7), planned_hours=4))
    assert row["is_planned"] is True


async def test_weekend_belongs_to_the_week_before(
    client: AsyncClient, db: AsyncSession, set_now: SetNow
) -> None:
    await login_as(client, db)
    refs = await make_linked(db)
    set_now(WEDNESDAY)
    # Saturday 2026-11-28 is in the week of Monday 23rd (still open on Wednesday 18th).
    row = await _create(client, _body(refs, date(2026, 11, 28), planned_hours=2))
    assert row["is_planned"] is True
    # Sunday 22nd is in the week under way.
    _locked(await client.post("/api/logs", json=_body(refs, date(2026, 11, 22), planned_hours=2)))


async def test_users_choose_planned_or_unplanned(
    client: AsyncClient, db: AsyncSession, set_now: SetNow
) -> None:
    me = await login_as(client, db)
    refs = await make_linked(db)
    set_now(WEDNESDAY)
    row = await _create(client, _body(refs, MONDAY, planned_hours=2))
    assert row["is_planned"] is True  # the default
    row = await _create(client, _body(refs, THIS_MONDAY, hours_spent=1, is_planned=False))
    assert row["is_planned"] is False

    # Changeable at any time, also in a locked week.
    log = await make_log(db, user=me, log_date=THIS_MONDAY, is_planned=False)
    resp = await client.patch(f"/api/logs/{log.id}", json={"is_planned": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_planned"] is True
    assert (await client.patch(f"/api/logs/{log.id}", json={"is_planned": None})).status_code == 422
    resp = await client.post("/api/logs", json=_body(refs, MONDAY, hours_spent=1, is_planned=None))
    assert resp.status_code == 422


# ---------------------------------------------------------------- locked weeks


async def test_locked_planned_hours_and_deletes(
    client: AsyncClient, db: AsyncSession, set_now: SetNow
) -> None:
    me = await login_as(client, db)
    refs = await make_linked(db)
    set_now(WEDNESDAY)
    planned = await _create(client, _body(refs, MONDAY, planned_hours=4))
    url = f"/api/logs/{planned['id']}"
    # While the week is open, planned hours change freely.
    assert (await client.patch(url, json={"planned_hours": 5})).status_code == 200

    set_now(AT_DEADLINE)
    _locked(await client.patch(url, json={"planned_hours": 6}))
    _locked(await client.patch(url, json={"planned_hours": None, "hours_spent": 5}))
    _locked(await client.patch(url, json={"log_date": (MONDAY + timedelta(days=7)).isoformat()}))
    _locked(await client.delete(url))
    reason = await db.scalar(select(DeviationReason.id).limit(1))
    # Actual hours, remarks and the deviation reason can change at any time, and
    # sending the unchanged planned hours (as the edit form does) is fine.
    resp = await client.patch(
        url,
        json={
            "planned_hours": 5,
            "hours_spent": 6,
            "description": "Took longer",
            "deviation_reason_id": reason,
            "is_planned": False,
        },
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["planned_hours"], resp.json()["hours_spent"]) == (5, 6)
    assert resp.json()["deviation_reason"]["id"] == reason
    # Still the week's plan (it holds planned hours), even when marked Unplanned.
    _locked(await client.delete(url))

    # Planned hours cannot be added to a row in a locked week either.
    unplanned = await make_log(db, user=me, log_date=MONDAY, is_planned=False, **refs.ids())
    _locked(await client.patch(f"/api/logs/{unplanned.id}", json={"planned_hours": 1}))
    # Rows without planned hours can be deleted.
    assert (await client.delete(f"/api/logs/{unplanned.id}")).status_code == 204


async def test_moving_planned_hours_into_a_locked_week(
    client: AsyncClient, db: AsyncSession, set_now: SetNow
) -> None:
    await login_as(client, db)
    refs = await make_linked(db)
    set_now(WEDNESDAY)
    row = await _create(client, _body(refs, MONDAY, planned_hours=4))
    resp = await client.patch(f"/api/logs/{row['id']}", json={"log_date": "2026-11-17"})
    _locked(resp)


async def test_admin_override(client: AsyncClient, db: AsyncSession, set_now: SetNow) -> None:
    admin = await login_as(client, db, role=Role.ADMIN)
    dev = await make_user(db)
    refs = await make_linked(db)
    set_now(AT_DEADLINE)

    # Admin can plan in a locked week.
    row = await _create(client, _body(refs, MONDAY, planned_hours=4))
    assert (row["is_planned"], row["planned_hours"]) == (True, 4)

    theirs = await make_log(
        db, user=dev, log_date=MONDAY, planned_hours=Decimal(3), is_planned=True, **refs.ids()
    )
    url = f"/api/logs/{theirs.id}"
    resp = await client.patch(url, json={"planned_hours": 2, "is_planned": False})
    assert resp.status_code == 200, resp.text
    assert (resp.json()["planned_hours"], resp.json()["is_planned"]) == (2, False)
    assert resp.json()["updated_by"]["id"] == admin.id
    assert (await client.patch(url, json={"is_planned": None})).status_code == 422
    assert (await client.delete(url)).status_code == 204


# ---------------------------------------------------------------- copy


async def test_copy_day_into_open_week(
    client: AsyncClient, db: AsyncSession, set_now: SetNow
) -> None:
    me = await login_as(client, db)
    refs = await make_linked(db)
    set_now(WEDNESDAY)
    source = THIS_MONDAY + timedelta(days=1)
    await make_log(
        db, user=me, log_date=source, hours_spent=Decimal(3), title="Review", **refs.ids()
    )
    await make_log(
        db,
        user=me,
        log_date=source,
        planned_hours=Decimal(2),
        hours_spent=Decimal(5),
        title=None,
        **refs.ids(),
    )
    # Tuesday already has 20 planned hours: the 5 copied hours would pass 24.
    await make_log(
        db,
        user=me,
        log_date=MONDAY + timedelta(days=1),
        planned_hours=Decimal(20),
        hours_spent=None,
        **refs.ids(),
    )
    targets = [MONDAY, MONDAY + timedelta(days=1), MONDAY + timedelta(days=2)]
    resp = await client.post(
        "/api/logs/copy",
        json={"from_date": source.isoformat(), "to_dates": [d.isoformat() for d in targets]},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["created"] == 4
    assert result["skipped_rows"] == 0
    assert [(d["date"], d["created"], d["skipped_reason"]) for d in result["days"]] == [
        ("2026-11-23", 2, None),
        ("2026-11-24", 0, "daily_hours_exceeded"),
        ("2026-11-25", 2, None),
    ]

    copies = (
        await client.get("/api/logs", params={"date_from": "2026-11-23", "date_to": "2026-11-23"})
    ).json()["items"]
    # Planned = source planned, else actual; no actual hours; planned rows; note kept.
    assert sorted(c["planned_hours"] for c in copies) == [2, 3]
    assert {c["hours_spent"] for c in copies} == {None}
    assert {c["is_planned"] for c in copies} == {True}
    assert {c["title"] for c in copies} == {"Review", None}


async def test_copy_only_into_open_weeks(
    client: AsyncClient, db: AsyncSession, set_now: SetNow
) -> None:
    me = await login_as(client, db, role=Role.ADMIN)  # admins too
    refs = await make_linked(db)
    await make_log(db, user=me, log_date=THIS_MONDAY, **refs.ids())
    set_now(AT_DEADLINE)
    resp = await client.post(
        "/api/logs/copy",
        json={"from_date": THIS_MONDAY.isoformat(), "to_dates": [MONDAY.isoformat()]},
    )
    _locked(resp)
    assert "to_dates" in resp.json()["error"]["fields"]


async def test_copy_week_maps_weekdays_and_skips_inactive(
    client: AsyncClient, db: AsyncSession, set_now: SetNow
) -> None:
    me = await login_as(client, db)
    refs = await make_linked(db)
    retired = await make_linked(db)
    retired.activity.is_active = False
    await db.flush()
    set_now(WEDNESDAY)
    await make_log(db, user=me, log_date=THIS_MONDAY, hours_spent=Decimal(8), **refs.ids())
    await make_log(
        db, user=me, log_date=THIS_MONDAY + timedelta(days=2), hours_spent=Decimal(6), **refs.ids()
    )
    await make_log(
        db, user=me, log_date=THIS_MONDAY + timedelta(days=2), **retired.ids()
    )  # left out
    await make_log(db, user=await make_user(db), log_date=THIS_MONDAY, **refs.ids())  # not mine

    week = [MONDAY + timedelta(days=i) for i in range(5)]
    resp = await client.post(
        "/api/logs/copy",
        json={"from_week": "2026-11-19", "to_dates": [d.isoformat() for d in week]},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["created"] == 2
    assert result["skipped_rows"] == 1
    assert [d["created"] for d in result["days"]] == [1, 0, 1, 0, 0]
    assert result["days"][1]["skipped_reason"] == "nothing_to_copy"

    status = (await client.get("/api/planning/status")).json()
    assert [d["planned_hours"] for d in status["days"]] == [8, 0, 6, 0, 0]


async def test_copy_validation(client: AsyncClient, db: AsyncSession, set_now: SetNow) -> None:
    await login_as(client, db)
    set_now(WEDNESDAY)
    day = MONDAY.isoformat()
    for body in (
        {"to_dates": [day]},
        {"from_date": "2026-11-17", "from_week": "2026-11-17", "to_dates": [day]},
        {"from_date": "2026-11-17", "to_dates": []},
        {"from_date": "2026-11-17", "to_dates": [day, day]},
        {"from_date": day, "to_dates": [day]},
    ):
        assert (await client.post("/api/logs/copy", json=body)).status_code == 422, body
    resp = await client.post("/api/logs/copy", json={"from_date": "2026-11-17", "to_dates": [day]})
    assert resp.json()["error"]["code"] == "nothing_to_copy"


# ---------------------------------------------------------------- status


async def test_own_status_and_reminder(
    client: AsyncClient, db: AsyncSession, set_now: SetNow
) -> None:
    me = await login_as(client, db)
    set_now(manila(DEADLINE_FRIDAY - timedelta(days=1), 23, 59))
    status = (await client.get("/api/planning/status")).json()
    assert (status["week_start"], status["week_end"]) == ("2026-11-23", "2026-11-27")
    assert status["deadline"].startswith("2026-11-20T10:30:00")  # UTC
    assert (status["is_open"], status["has_planned"], status["show_reminder"]) == (
        True,
        False,
        False,
    )
    assert status["workday_hours"] == 8

    set_now(manila(DEADLINE_FRIDAY, 0, 0))
    assert (await client.get("/api/planning/status")).json()["show_reminder"] is True

    await make_log(db, user=me, log_date=MONDAY, planned_hours=Decimal(6), hours_spent=None)
    await make_log(db, user=me, log_date=MONDAY, planned_hours=Decimal(2), hours_spent=None)
    await make_log(db, user=me, log_date=MONDAY + timedelta(days=4))  # actual only
    status = (await client.get("/api/planning/status")).json()
    assert (status["has_planned"], status["show_reminder"], status["total"]) == (True, False, 8)
    assert [d["planned_hours"] for d in status["days"]] == [8, 0, 0, 0, 0]

    # After the deadline the week is locked and the reminder is gone.
    set_now(AT_DEADLINE)
    other = (await client.get("/api/planning/status", params={"week": "2026-11-25"})).json()
    assert other["is_open"] is False
    # Any date in a week picks that week.
    assert other["week_start"] == "2026-11-23"


async def test_team_status_scoping(client: AsyncClient, db: AsyncSession, set_now: SetNow) -> None:
    team, other_team = await make_team(db), await make_team(db)
    set_now(WEDNESDAY)
    planner = await make_user(db, team=team, username="aa_planner")
    idle = await make_user(db, team=team, username="bb_idle")
    await make_user(db, team=team, username="zz_gone", is_active=False)
    await make_log(db, user=planner, log_date=MONDAY, planned_hours=Decimal(8), hours_spent=None)
    await make_log(db, user=await make_user(db, team=other_team), log_date=MONDAY, planned_hours=1)

    dev = await login_as(client, db, role=Role.DEV, team=team)
    assert (await client.get(f"/api/teams/{team.id}/planning/status")).status_code == 403

    manager = await login_as(client, db, role=Role.MANAGER, team=team)
    assert (await client.get(f"/api/teams/{other_team.id}/planning/status")).status_code == 404
    status = (await client.get(f"/api/teams/{team.id}/planning/status")).json()
    assert status["week_start"] == "2026-11-23"
    members = {m["member"]["username"]: m for m in status["members"]}
    assert set(members) == {"aa_planner", "bb_idle", dev.username, manager.username}
    assert members["aa_planner"]["has_planned"] is True
    assert [d["planned_hours"] for d in members["aa_planner"]["days"]] == [8, 0, 0, 0, 0]
    assert (members["bb_idle"]["has_planned"], members["bb_idle"]["total"]) == (False, 0)
    assert idle.id == members["bb_idle"]["member"]["id"]

    await login_as(client, db, role=Role.ADMIN)
    resp = await client.get(f"/api/teams/{other_team.id}/planning/status")
    assert resp.status_code == 200
    assert [m["has_planned"] for m in resp.json()["members"]] == [True]
    assert (await client.get("/api/teams/999999/planning/status")).status_code == 404
