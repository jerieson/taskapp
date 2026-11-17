"""Daily plans: ownership, open-task rule, duplicates, ordering, hours, replace-all."""

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import DailyPlan, DailyPlanItem, Role, Task, User
from tests.auth_helpers import login_as
from tests.factories import make_status, make_task, make_user

pytestmark = pytest.mark.anyio

DAY = date(2026, 11, 17)


async def _open(client: AsyncClient, plan_date: date = DAY) -> dict:
    resp = await client.post("/api/plans", json={"plan_date": plan_date.isoformat()})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _add(client: AsyncClient, plan_id: int, task: Task, **kw: object) -> dict:
    resp = await client.post(f"/api/plans/{plan_id}/items", json={"task_id": task.id, **kw})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _done_task(db: AsyncSession, user: User) -> Task:
    return await make_task(db, user=user, status_id=(await make_status(db, is_done=True)).id)


# ---------------------------------------------------------------- get or create


async def test_endpoints_require_login(client: AsyncClient) -> None:
    assert (await client.get("/api/plans/1")).status_code == 401
    assert (await client.get(f"/api/plans/by-date/{DAY}")).status_code == 401


async def test_open_plan_creates_once(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    first = await _open(client)
    second = await _open(client)
    assert first["id"] == second["id"]
    assert first["plan_date"] == DAY.isoformat()
    assert first["items"] == []
    assert first["ai_generated"] is False
    assert first["total_hours"] == 0
    assert first["workday_hours"] == float(get_settings().workday_hours)
    count = await db.scalar(select(func.count()).where(DailyPlan.user_id == me.id))
    assert count == 1


async def test_get_by_date(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    assert (await client.get(f"/api/plans/by-date/{DAY}")).status_code == 404
    plan = await _open(client)
    resp = await client.get(f"/api/plans/by-date/{DAY}")
    assert resp.status_code == 200
    assert resp.json()["id"] == plan["id"]


async def test_same_date_plans_are_per_user(
    client: AsyncClient, new_client, db: AsyncSession
) -> None:
    await login_as(client, db)
    other = new_client()
    await login_as(other, db)
    assert (await _open(client))["id"] != (await _open(other))["id"]


@pytest.mark.parametrize("role", [Role.ADMIN, Role.MANAGER, Role.DEV])
async def test_another_users_plan_is_404(client: AsyncClient, db: AsyncSession, role: Role) -> None:
    owner = await make_user(db)
    task = await make_task(db, user=owner)
    plan = DailyPlan(user_id=owner.id, plan_date=DAY)
    db.add(plan)
    await db.flush()
    item = DailyPlanItem(daily_plan_id=plan.id, task_id=task.id, item_order=0)
    db.add(item)
    await db.flush()

    me = await login_as(client, db, role=role)
    my_task = await make_task(db, user=me)
    base = f"/api/plans/{plan.id}"
    responses = [
        await client.get(base),
        await client.post(f"{base}/items", json={"task_id": my_task.id}),
        await client.put(f"{base}/items", json={"items": []}),
        await client.put(f"{base}/order", json={"item_ids": [item.id]}),
        await client.patch(f"{base}/items/{item.id}", json={"suggested_hours": 1}),
        await client.delete(f"{base}/items/{item.id}"),
    ]
    assert [r.status_code for r in responses] == [404] * len(responses)
    # The owner's plan for that date is not returned by date either.
    assert (await client.get(f"/api/plans/by-date/{DAY}")).status_code == 404
    assert await db.scalar(select(func.count()).where(DailyPlanItem.id == item.id)) == 1


async def test_item_of_another_plan_is_404(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    task = await make_task(db, user=me)
    other_day = await _open(client, date(2026, 11, 18))
    item = (await _add(client, other_day["id"], task))["items"][0]
    plan = await _open(client)
    resp = await client.patch(
        f"/api/plans/{plan['id']}/items/{item['id']}", json={"suggested_hours": 1}
    )
    assert resp.status_code == 404
    assert (await client.delete(f"/api/plans/{plan['id']}/items/{item['id']}")).status_code == 404


# ---------------------------------------------------------------- adding items


async def test_add_items_in_order_with_task_details(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    first = await make_task(db, user=me)
    second = await make_task(db, user=me)
    plan = await _open(client)
    await _add(client, plan["id"], first, suggested_hours=1.5)
    body = await _add(client, plan["id"], second, suggested_hours=2)

    assert [i["task"]["id"] for i in body["items"]] == [first.id, second.id]
    assert [i["item_order"] for i in body["items"]] == [0, 1]
    assert body["items"][0]["suggested_hours"] == 1.5
    assert body["items"][0]["task"]["title"] == first.title
    assert body["total_hours"] == 3.5


async def test_cannot_add_another_users_task(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    task = await make_task(db, user=await make_user(db))
    plan = await _open(client)
    resp = await client.post(f"/api/plans/{plan['id']}/items", json={"task_id": task.id})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_reference"
    assert "task_id" in resp.json()["error"]["fields"]


async def test_cannot_add_completed_task(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    task = await _done_task(db, me)
    plan = await _open(client)
    resp = await client.post(f"/api/plans/{plan['id']}/items", json={"task_id": task.id})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_reference"


async def test_cannot_add_missing_task(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    plan = await _open(client)
    resp = await client.post(f"/api/plans/{plan['id']}/items", json={"task_id": 999999})
    assert resp.status_code == 422


async def test_duplicate_rejected(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    task = await make_task(db, user=me)
    plan = await _open(client)
    await _add(client, plan["id"], task)
    resp = await client.post(f"/api/plans/{plan['id']}/items", json={"task_id": task.id})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "duplicate_task"
    assert resp.json()["error"]["fields"] == {"task_id": "This task is already in the plan"}


async def test_same_task_in_plans_of_different_days(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    task = await make_task(db, user=me)
    await _add(client, (await _open(client))["id"], task)
    await _add(client, (await _open(client, date(2026, 11, 18)))["id"], task)


@pytest.mark.parametrize("hours", [0, -1, 24.01, 1.234])
async def test_invalid_hours_rejected(client: AsyncClient, db: AsyncSession, hours: float) -> None:
    me = await login_as(client, db)
    task = await make_task(db, user=me)
    plan = await _open(client)
    resp = await client.post(
        f"/api/plans/{plan['id']}/items", json={"task_id": task.id, "suggested_hours": hours}
    )
    assert resp.status_code == 422
    assert "suggested_hours" in resp.json()["error"]["fields"]


async def test_completed_task_stays_in_plan(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    task = await make_task(db, user=me)
    plan = await _open(client)
    await _add(client, plan["id"], task)
    done = await make_status(db, is_done=True)
    resp = await client.patch(f"/api/tasks/{task.id}", json={"status_id": done.id})
    assert resp.status_code == 200

    body = (await client.get(f"/api/plans/{plan['id']}")).json()
    assert body["items"][0]["task"]["status"]["is_done"] is True


async def test_deleting_task_removes_item(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    task = await make_task(db, user=me)
    plan = await _open(client)
    await _add(client, plan["id"], task)
    assert (await client.delete(f"/api/tasks/{task.id}")).status_code == 204
    assert (await client.get(f"/api/plans/{plan['id']}")).json()["items"] == []


# ---------------------------------------------------------------- edit, remove, reorder


async def test_update_hours(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    task = await make_task(db, user=me)
    plan = await _open(client)
    item = (await _add(client, plan["id"], task))["items"][0]
    url = f"/api/plans/{plan['id']}/items/{item['id']}"

    resp = await client.patch(url, json={"suggested_hours": 2.25})
    assert resp.status_code == 200
    assert resp.json()["items"][0]["suggested_hours"] == 2.25
    assert resp.json()["total_hours"] == 2.25

    resp = await client.patch(url, json={"suggested_hours": None})
    assert resp.json()["items"][0]["suggested_hours"] is None
    assert resp.json()["total_hours"] == 0


async def test_remove_renumbers(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    tasks = [await make_task(db, user=me) for _ in range(3)]
    plan = await _open(client)
    for task in tasks:
        body = await _add(client, plan["id"], task)
    middle = body["items"][1]["id"]

    assert (await client.delete(f"/api/plans/{plan['id']}/items/{middle}")).status_code == 204
    items = (await client.get(f"/api/plans/{plan['id']}")).json()["items"]
    assert [i["task"]["id"] for i in items] == [tasks[0].id, tasks[2].id]
    assert [i["item_order"] for i in items] == [0, 1]
    # The task itself is untouched.
    assert await db.get(Task, tasks[1].id) is not None


async def test_reorder(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    tasks = [await make_task(db, user=me) for _ in range(3)]
    plan = await _open(client)
    for task in tasks:
        body = await _add(client, plan["id"], task)
    ids = [i["id"] for i in body["items"]]

    resp = await client.put(f"/api/plans/{plan['id']}/order", json={"item_ids": ids[::-1]})
    assert resp.status_code == 200
    assert [i["task"]["id"] for i in resp.json()["items"]] == [t.id for t in tasks[::-1]]
    assert [i["item_order"] for i in resp.json()["items"]] == [0, 1, 2]


@pytest.mark.parametrize("change", ["missing", "extra", "repeat"])
async def test_reorder_must_list_every_item_once(
    client: AsyncClient, db: AsyncSession, change: str
) -> None:
    me = await login_as(client, db)
    plan = await _open(client)
    for _ in range(2):
        body = await _add(client, plan["id"], await make_task(db, user=me))
    ids = [i["id"] for i in body["items"]]
    item_ids = {"missing": ids[:1], "extra": [*ids, 999999], "repeat": [ids[0], *ids]}[change]
    resp = await client.put(f"/api/plans/{plan['id']}/order", json={"item_ids": item_ids})
    assert resp.status_code == 422


# ---------------------------------------------------------------- replace all


async def test_replace_items(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    keep, drop, new = [await make_task(db, user=me) for _ in range(3)]
    plan = await _open(client)
    await _add(client, plan["id"], keep, suggested_hours=1)
    await _add(client, plan["id"], drop)

    resp = await client.put(
        f"/api/plans/{plan['id']}/items",
        json={
            "items": [
                {"task_id": new.id, "suggested_hours": 3},
                {"task_id": keep.id},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [i["task"]["id"] for i in items] == [new.id, keep.id]
    assert [i["suggested_hours"] for i in items] == [3, None]
    assert resp.json()["total_hours"] == 3


async def test_replace_with_empty_list_clears(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    plan = await _open(client)
    await _add(client, plan["id"], await make_task(db, user=me))
    resp = await client.put(f"/api/plans/{plan['id']}/items", json={"items": []})
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.parametrize("bad", ["other_user", "completed", "duplicate"])
async def test_replace_is_all_or_nothing(client: AsyncClient, db: AsyncSession, bad: str) -> None:
    me = await login_as(client, db)
    existing = await make_task(db, user=me)
    fine = await make_task(db, user=me)
    plan = await _open(client)
    await _add(client, plan["id"], existing)

    if bad == "other_user":
        bad_id = (await make_task(db, user=await make_user(db))).id
    elif bad == "completed":
        bad_id = (await _done_task(db, me)).id
    else:
        bad_id = fine.id
    resp = await client.put(
        f"/api/plans/{plan['id']}/items",
        json={"items": [{"task_id": fine.id}, {"task_id": bad_id}]},
    )
    assert resp.status_code == 422
    items = (await client.get(f"/api/plans/{plan['id']}")).json()["items"]
    assert [i["task"]["id"] for i in items] == [existing.id]
