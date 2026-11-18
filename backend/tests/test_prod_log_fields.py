"""Prod log fields from the team's sheet: linked dropdowns, work set-up, planned and
actual hours with separate daily caps, and the new list fields and filters."""

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WorkSetup
from tests.auth_helpers import login_as
from tests.factories import (
    LinkedRefs,
    make_activity,
    make_activity_group,
    make_category,
    make_deviation_reason,
    make_linked,
    make_log,
    make_om_project,
    make_project,
    make_work_setup,
)

pytestmark = pytest.mark.anyio

TODAY = date.today()


@pytest.fixture(autouse=True)
def _week_open(set_now: Callable[[datetime], None]) -> None:
    """Planned hours are only accepted in open weeks: put the clock two weeks back."""
    monday_before = TODAY - timedelta(days=TODAY.weekday() + 14)
    set_now(datetime.combine(monday_before, time(12), tzinfo=UTC))


@pytest.fixture(autouse=True)
def _daily_cap(settings_override: Callable[..., object]) -> None:
    """Daily totals are capped at WORKDAY_HOURS; pin it so the numbers below hold."""
    settings_override(workday_hours=Decimal(9))


def _body(refs: LinkedRefs, **kw: object) -> dict[str, object]:
    return {"log_date": TODAY.isoformat(), "hours_spent": 2, **refs.ids(), **kw}


async def _create(client: AsyncClient, body: dict[str, object]) -> dict[str, object]:
    resp = await client.post("/api/logs", json=body)
    assert resp.status_code == 201, resp.text
    data: dict[str, object] = resp.json()
    return data


def _field_error(resp: Response, field: str) -> None:
    assert resp.status_code == 422, resp.text
    assert field in resp.json()["error"]["fields"]


# ---------------------------------------------------------------- create


async def test_create_with_all_fields(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    refs = await make_linked(db, requires_om_project=True)
    om = await make_om_project(db)
    setup = await make_work_setup(db)
    reason = await make_deviation_reason(db)
    body = await _create(
        client,
        _body(
            refs,
            work_setup_id=setup.id,
            planned_hours="3.5",
            hours_spent=4,
            om_project_id=om.id,
            title="UAT round 2",
            description="With the client",
            deviation_reason_id=reason.id,
        ),
    )
    assert body["work_setup"]["id"] == setup.id  # type: ignore[index]
    assert body["activity"]["id"] == refs.activity.id  # type: ignore[index]
    assert body["om_project"] == {"id": om.id, "label": om.label, "is_active": True}
    assert (body["planned_hours"], body["hours_spent"], body["is_planned"]) == (3.5, 4, True)
    assert body["deviation_reason"] == {"id": reason.id, "label": reason.label, "is_active": True}


async def test_minimal_row_gets_default_work_setup_and_no_title(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login_as(client, db)
    refs = await make_linked(db)
    default = await db.scalar(select(WorkSetup).where(WorkSetup.is_default))
    assert default is not None
    body = await _create(client, _body(refs))
    assert body["work_setup"]["id"] == default.id  # type: ignore[index]
    # Planned (the week is open) even without planned hours.
    assert (body["title"], body["planned_hours"], body["is_planned"]) == (None, None, True)
    assert body["om_project"] is None


async def test_no_default_work_setup_is_409(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    refs = await make_linked(db)
    await db.execute(update(WorkSetup).values(is_default=False))
    resp = await client.post("/api/logs", json=_body(refs))
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "no_default_work_setup"


async def test_planned_only_row(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    refs = await make_linked(db)
    body = await _create(client, _body(refs, hours_spent=None, planned_hours=8))
    assert (body["planned_hours"], body["hours_spent"], body["is_planned"]) == (8, None, True)


async def test_hours_required(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    refs = await make_linked(db)
    resp = await client.post("/api/logs", json=_body(refs, hours_spent=None))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "hours_required"
    assert "hours_spent" in resp.json()["error"]["fields"]

    # Clearing the only hours on update is rejected too; swapping them is fine.
    log = await make_log(db, user=me, hours_spent=Decimal("2"))
    resp = await client.patch(f"/api/logs/{log.id}", json={"hours_spent": None})
    assert resp.json()["error"]["code"] == "hours_required"
    resp = await client.patch(f"/api/logs/{log.id}", json={"hours_spent": None, "planned_hours": 2})
    assert resp.status_code == 200, resp.text
    # Planned/Unplanned does not follow the hours.
    assert resp.json()["is_planned"] is True


async def test_planned_hours_validation(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    refs = await make_linked(db)
    for hours in (0, -1, 24.5, "1.234"):
        _field_error(
            await client.post("/api/logs", json=_body(refs, planned_hours=hours)), "planned_hours"
        )


@pytest.mark.parametrize("field", ["activity_id", "work_setup_id", "om_project_id"])
async def test_inactive_new_refs_rejected(
    client: AsyncClient, db: AsyncSession, field: str
) -> None:
    await login_as(client, db)
    refs = await make_linked(db, requires_om_project=True)
    if field == "activity_id":
        value = refs.activity.id
        refs.activity.is_active = False
    elif field == "work_setup_id":
        value = (await make_work_setup(db, is_active=False)).id
    else:
        value = (await make_om_project(db, is_active=False)).id
    await db.flush()
    _field_error(await client.post("/api/logs", json=_body(refs, **{field: value})), field)


async def test_activity_is_required(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    refs = await make_linked(db)
    body = _body(refs)
    del body["activity_id"]
    _field_error(await client.post("/api/logs", json=body), "activity_id")


# ---------------------------------------------------------------- linked dropdowns


async def test_project_must_be_under_category(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    refs = await make_linked(db)
    other = await make_category(db)
    resp = await client.post("/api/logs", json=_body(refs, category_id=other.id))
    _field_error(resp, "project_id")


async def test_activity_must_be_in_projects_group(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    refs = await make_linked(db)
    stray = await make_activity(db)
    _field_error(
        await client.post("/api/logs", json=_body(refs, activity_id=stray.id)), "activity_id"
    )

    # A project without a group offers no activities.
    bare = await make_project(db, categories=[refs.category])
    _field_error(
        await client.post("/api/logs", json=_body(refs, project_id=bare.id)), "activity_id"
    )


async def test_activity_in_several_groups(client: AsyncClient, db: AsyncSession) -> None:
    """An activity shared by two groups is valid for projects of either group."""
    await login_as(client, db)
    refs = await make_linked(db)
    group = await make_activity_group(db, activities=[refs.activity])
    project = await make_project(db, categories=[refs.category], activity_group_id=group.id)
    await _create(client, _body(refs, project_id=project.id))


async def test_om_project_only_for_categories_that_offer_it(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login_as(client, db)
    om = await make_om_project(db)
    plain = await make_linked(db)
    _field_error(
        await client.post("/api/logs", json=_body(plain, om_project_id=om.id)), "om_project_id"
    )

    # Optional even where offered.
    offering = await make_linked(db, requires_om_project=True)
    await _create(client, _body(offering))
    await _create(client, _body(offering, om_project_id=om.id))


async def test_update_checks_links_for_changed_values(
    client: AsyncClient, db: AsyncSession
) -> None:
    me = await login_as(client, db)
    refs = await make_linked(db)
    log_id = (await _create(client, _body(refs)))["id"]
    url = f"/api/logs/{log_id}"

    other = await make_linked(db)
    _field_error(await client.patch(url, json={"category_id": other.category.id}), "project_id")
    _field_error(await client.patch(url, json={"project_id": other.project.id}), "project_id")
    sibling = await make_project(db, categories=[refs.category], activity_group_id=other.group.id)
    _field_error(await client.patch(url, json={"project_id": sibling.id}), "activity_id")
    _field_error(await client.patch(url, json={"activity_id": other.activity.id}), "activity_id")
    resp = await client.patch(url, json=other.ids())
    assert resp.status_code == 200, resp.text

    # An O&M project on a category that doesn't offer one.
    om = await make_om_project(db)
    _field_error(await client.patch(url, json={"om_project_id": om.id}), "om_project_id")
    assert me.id == resp.json()["user"]["id"]


async def test_update_keeps_unchanged_pairs_after_links_change(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Old rows (and rows whose links the admin removed later) stay editable."""
    me = await login_as(client, db)
    om = await make_om_project(db)
    unlinked_category = await make_category(db)
    log = await make_log(
        db,
        user=me,
        category_id=unlinked_category.id,
        project_id=(await make_project(db)).id,
        om_project_id=om.id,
    )
    resp = await client.patch(f"/api/logs/{log.id}", json={"hours_spent": 3, "title": "Still fine"})
    assert resp.status_code == 200, resp.text
    # Sending the same values back counts as unchanged.
    resp = await client.patch(
        f"/api/logs/{log.id}",
        json={
            "category_id": log.category_id,
            "project_id": log.project_id,
            "activity_id": log.activity_id,
            "om_project_id": om.id,
        },
    )
    assert resp.status_code == 200, resp.text
    # A pre-Phase-15 row without a project can be edited without adding one ...
    no_project = await make_log(db, user=me)
    assert (
        await client.patch(f"/api/logs/{no_project.id}", json={"hours_spent": 2})
    ).status_code == 200
    # ... but the project cannot be cleared on purpose.
    refs = await make_linked(db)
    row = await _create(client, _body(refs))
    resp = await client.patch(f"/api/logs/{row['id']}", json={"project_id": None})
    assert resp.status_code == 422


# ---------------------------------------------------------------- daily caps


async def test_actual_and_planned_caps_are_separate(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    refs = await make_linked(db)
    await make_log(db, user=me, hours_spent=Decimal("5"), planned_hours=Decimal("5"))
    await make_log(db, user=me, hours_spent=None, planned_hours=Decimal("4"))

    # 4 more actual is fine (planned-only rows don't count toward actual) ...
    await _create(client, _body(refs, hours_spent=4))
    # ... but the planned total is full.
    resp = await client.post("/api/logs", json=_body(refs, hours_spent=None, planned_hours=0.25))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "daily_hours_exceeded"
    assert "planned_hours" in resp.json()["error"]["fields"]
    # The actual total is full now as well.
    resp = await client.post("/api/logs", json=_body(refs, hours_spent=0.25))
    assert resp.json()["error"]["fields"].keys() == {"hours_spent"}
    # Other days are separate.
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    await _create(client, _body(refs, log_date=yesterday, planned_hours=9, hours_spent=9))


async def test_planned_cap_on_update(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    await make_log(db, user=me, hours_spent=None, planned_hours=Decimal("5"))
    log = await make_log(db, user=me, hours_spent=Decimal("1"), planned_hours=Decimal("4"))
    # Its own planned hours are not double-counted; actual edits don't check planned.
    assert (await client.patch(f"/api/logs/{log.id}", json={"hours_spent": 5})).status_code == 200
    resp = await client.patch(f"/api/logs/{log.id}", json={"planned_hours": 4.5})
    assert resp.status_code == 422
    assert "planned_hours" in resp.json()["error"]["fields"]


# ---------------------------------------------------------------- lists


async def test_list_fields_filters_and_day_totals(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    activity = await make_activity(db)
    a = await make_log(db, user=me, hours_spent=Decimal("2"), planned_hours=Decimal("3"))
    b = await make_log(db, user=me, hours_spent=None, planned_hours=Decimal("4"))
    c = await make_log(db, user=me, hours_spent=Decimal("1.5"), activity_id=activity.id)

    items = (await client.get("/api/logs")).json()["items"]
    assert [i["id"] for i in items] == [c.id, b.id, a.id]
    assert {i["day_total_hours"] for i in items} == {3.5}
    assert {i["day_planned_hours"] for i in items} == {7}
    by_id = {i["id"]: i for i in items}
    assert by_id[b.id]["hours_spent"] is None
    assert by_id[c.id]["activity"]["id"] == activity.id
    assert by_id[c.id]["work_setup"]["label"]

    resp = await client.get("/api/logs", params={"activity_id": activity.id})
    assert [i["id"] for i in resp.json()["items"]] == [c.id]
