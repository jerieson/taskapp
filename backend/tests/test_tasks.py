"""Tasks: ownership, defaults, completed_at, active-value rules, filters and sorting."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Priority,
    Process,
    ProcessRun,
    Role,
    Status,
    Task,
)
from tests.auth_helpers import login_as
from tests.factories import (
    make_category,
    make_priority,
    make_project,
    make_status,
    make_task,
    make_user,
)

pytestmark = pytest.mark.anyio


async def _defaults(db: AsyncSession) -> tuple[Status, Priority]:
    """Fresh default status and priority (any existing default loses the flag)."""
    for model in (Status, Priority):
        for row in await db.scalars(select(model).where(model.is_default)):
            row.is_default = False
    await db.flush()
    return await make_status(db, is_default=True), await make_priority(db, is_default=True)


# ---------------------------------------------------------------- access control


async def test_endpoints_require_login(client: AsyncClient) -> None:
    assert (await client.get("/api/tasks")).status_code == 401
    assert (await client.get("/api/tasks/1")).status_code == 401


@pytest.mark.parametrize("role", [Role.ADMIN, Role.MANAGER, Role.DEV])
async def test_cannot_touch_another_users_task(
    client: AsyncClient, db: AsyncSession, role: Role
) -> None:
    other = await make_user(db)
    task = await make_task(db, user=other)
    me = await login_as(client, db, role=role)
    if role != Role.ADMIN:
        # Even a teammate (or their manager) cannot see it.
        other.team_id = me.team_id
        await db.flush()

    url = f"/api/tasks/{task.id}"
    assert (await client.get(url)).status_code == 404
    assert (await client.patch(url, json={"title": "Mine now"})).status_code == 404
    assert (await client.delete(url)).status_code == 404
    listed = (await client.get("/api/tasks")).json()
    assert task.id not in [t["id"] for t in listed["items"]]

    await db.refresh(task)
    assert task.title != "Mine now"
    assert task.user_id == other.id


async def test_missing_task_is_404(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    resp = await client.get("/api/tasks/999999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


# ---------------------------------------------------------------- create


async def test_create_uses_defaults(client: AsyncClient, db: AsyncSession) -> None:
    status, priority = await _defaults(db)
    user = await login_as(client, db)
    resp = await client.post("/api/tasks", json={"title": "  Write tests  "})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Write tests"
    assert body["status"]["id"] == status.id
    assert body["priority"]["id"] == priority.id
    assert body["completed_at"] is None
    assert body["project"] is None
    assert body["category"] is None
    task = await db.get(Task, body["id"])
    assert task is not None
    assert task.user_id == user.id


async def test_create_with_all_fields(client: AsyncClient, db: AsyncSession) -> None:
    await _defaults(db)
    status = await make_status(db)
    priority = await make_priority(db)
    category = await make_category(db, color="#AABBCC")
    project = await make_project(db)
    await login_as(client, db)
    due = (date.today() + timedelta(days=3)).isoformat()
    resp = await client.post(
        "/api/tasks",
        json={
            "title": "Full",
            "description": "Details",
            "status_id": status.id,
            "priority_id": priority.id,
            "category_id": category.id,
            "project_id": project.id,
            "due_date": due,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"]["id"] == status.id
    assert body["priority"]["id"] == priority.id
    assert body["category"] == {
        "id": category.id,
        "label": category.label,
        "color": "#AABBCC",
        "is_active": True,
    }
    assert body["project"] == {"id": project.id, "name": project.name, "is_active": True}
    assert body["due_date"] == due
    assert body["is_overdue"] is False


@pytest.mark.parametrize("field", ["status_id", "priority_id", "category_id", "project_id"])
async def test_create_rejects_inactive_values(
    client: AsyncClient, db: AsyncSession, field: str
) -> None:
    await _defaults(db)
    factory = {
        "status_id": make_status,
        "priority_id": make_priority,
        "category_id": make_category,
        "project_id": make_project,
    }[field]
    inactive = await factory(db, is_active=False)
    await login_as(client, db)
    resp = await client.post("/api/tasks", json={"title": "x", field: inactive.id})
    assert resp.status_code == 422
    assert field in resp.json()["error"]["fields"]


async def test_create_rejects_unknown_values(client: AsyncClient, db: AsyncSession) -> None:
    await _defaults(db)
    await login_as(client, db)
    resp = await client.post("/api/tasks", json={"title": "x", "category_id": 999999})
    assert resp.status_code == 422
    assert "category_id" in resp.json()["error"]["fields"]


async def test_create_without_default_is_409(client: AsyncClient, db: AsyncSession) -> None:
    for model in (Status, Priority):
        for row in await db.scalars(select(model).where(model.is_default)):
            row.is_default = False
    await db.flush()
    await login_as(client, db)
    resp = await client.post("/api/tasks", json={"title": "x"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "no_default_status"


async def test_create_validates_title(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    resp = await client.post("/api/tasks", json={"title": "   "})
    assert resp.status_code == 422
    assert "title" in resp.json()["error"]["fields"]


# ---------------------------------------------------------------- completed_at


async def test_completed_at_set_and_cleared(client: AsyncClient, db: AsyncSession) -> None:
    open_status, _ = await _defaults(db)
    done = await make_status(db, is_done=True)
    done_too = await make_status(db, is_done=True)
    await login_as(client, db)
    task_id = (await client.post("/api/tasks", json={"title": "x"})).json()["id"]
    url = f"/api/tasks/{task_id}"

    body = (await client.patch(url, json={"status_id": done.id})).json()
    completed_at = body["completed_at"]
    assert completed_at is not None

    # Another done status keeps the original completion time.
    body = (await client.patch(url, json={"status_id": done_too.id})).json()
    assert body["completed_at"] == completed_at

    # Editing other fields does not touch it either.
    body = (await client.patch(url, json={"title": "renamed"})).json()
    assert body["completed_at"] == completed_at

    body = (await client.patch(url, json={"status_id": open_status.id})).json()
    assert body["completed_at"] is None


async def test_create_with_done_status_sets_completed_at(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _defaults(db)
    done = await make_status(db, is_done=True)
    await login_as(client, db)
    resp = await client.post("/api/tasks", json={"title": "x", "status_id": done.id})
    assert resp.json()["completed_at"] is not None


# ---------------------------------------------------------------- update


async def test_update_keeps_assigned_inactive_values(client: AsyncClient, db: AsyncSession) -> None:
    user = await login_as(client, db)
    category = await make_category(db)
    project = await make_project(db)
    task = await make_task(db, user=user, category_id=category.id, project_id=project.id)
    status = await db.get(Status, task.status_id)
    assert status is not None
    for row in (category, project, status):
        row.is_active = False
    await db.flush()

    url = f"/api/tasks/{task.id}"
    resp = await client.patch(
        url,
        json={
            "title": "still fine",
            "category_id": category.id,
            "project_id": project.id,
            "status_id": status.id,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["category"]["is_active"] is False
    assert body["project"]["is_active"] is False

    # Choosing a different inactive value is rejected.
    other = await make_category(db, is_active=False)
    resp = await client.patch(url, json={"category_id": other.id})
    assert resp.status_code == 422
    assert "category_id" in resp.json()["error"]["fields"]


async def test_update_clears_optional_fields(client: AsyncClient, db: AsyncSession) -> None:
    user = await login_as(client, db)
    category = await make_category(db)
    task = await make_task(
        db, user=user, category_id=category.id, description="d", due_date=date.today()
    )
    resp = await client.patch(
        f"/api/tasks/{task.id}",
        json={"category_id": None, "description": None, "due_date": None},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] is None
    assert body["description"] is None
    assert body["due_date"] is None


@pytest.mark.parametrize("field", ["title", "status_id", "priority_id"])
async def test_update_rejects_null_required(
    client: AsyncClient, db: AsyncSession, field: str
) -> None:
    user = await login_as(client, db)
    task = await make_task(db, user=user)
    resp = await client.patch(f"/api/tasks/{task.id}", json={field: None})
    assert resp.status_code == 422


# ---------------------------------------------------------------- delete


async def test_delete(client: AsyncClient, db: AsyncSession) -> None:
    user = await login_as(client, db)
    task = await make_task(db, user=user)

    assert (await client.delete(f"/api/tasks/{task.id}")).status_code == 204
    db.expunge_all()
    assert await db.get(Task, task.id) is None


# ---------------------------------------------------------------- list


async def test_overdue_flag(client: AsyncClient, db: AsyncSession) -> None:
    user = await login_as(client, db)
    yesterday = date.today() - timedelta(days=2)
    late = await make_task(db, user=user, due_date=yesterday)
    done = await make_status(db, is_done=True)
    late_done = await make_task(db, user=user, due_date=yesterday, status_id=done.id)
    on_time = await make_task(db, user=user, due_date=date.today() + timedelta(days=2))
    items = {t["id"]: t for t in (await client.get("/api/tasks")).json()["items"]}
    assert items[late.id]["is_overdue"] is True
    assert items[late_done.id]["is_overdue"] is False
    assert items[on_time.id]["is_overdue"] is False


async def test_filters(client: AsyncClient, db: AsyncSession) -> None:
    user = await login_as(client, db)
    done = await make_status(db, is_done=True)
    category = await make_category(db)
    project = await make_project(db)
    today = date.today()

    a = await make_task(db, user=user, category_id=category.id, due_date=today)
    b = await make_task(db, user=user, project_id=project.id, status_id=done.id)
    c = await make_task(db, user=user, due_date=today + timedelta(days=10))
    await make_task(db)  # someone else's

    async def ids(**query: object) -> set[int]:
        resp = await client.get("/api/tasks", params=query)
        assert resp.status_code == 200, resp.text
        return {t["id"] for t in resp.json()["items"]}

    assert await ids() == {a.id, b.id, c.id}
    assert await ids(category_id=category.id) == {a.id}
    assert await ids(project_id=project.id) == {b.id}
    assert await ids(status_id=done.id) == {b.id}
    assert await ids(priority_id=a.priority_id) == {a.id}
    assert await ids(state="completed") == {b.id}
    assert await ids(state="open") == {a.id, c.id}
    assert await ids(due_from=today.isoformat()) == {a.id, c.id}
    assert await ids(due_to=(today + timedelta(days=1)).isoformat()) == {a.id}
    assert await ids(in_process_run="false") == {a.id, b.id, c.id}
    assert await ids(in_process_run="true") == set()


async def test_filter_by_process_run(client: AsyncClient, db: AsyncSession) -> None:
    user = await login_as(client, db)
    process = Process(owner_id=user.id, name="Release")
    db.add(process)
    await db.flush()
    run = ProcessRun(process_id=process.id, user_id=user.id)
    db.add(run)
    await db.flush()
    in_run = await make_task(db, user=user, process_run_id=run.id)
    await make_task(db, user=user)

    resp = await client.get("/api/tasks", params={"process_run_id": run.id})
    assert [t["id"] for t in resp.json()["items"]] == [in_run.id]
    resp = await client.get("/api/tasks", params={"in_process_run": "true"})
    assert [t["id"] for t in resp.json()["items"]] == [in_run.id]


async def test_bad_due_range_is_422(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    resp = await client.get("/api/tasks", params={"due_from": "2026-02-02", "due_to": "2026-01-01"})
    assert resp.status_code == 422


async def test_sorting(client: AsyncClient, db: AsyncSession) -> None:
    user = await login_as(client, db)
    low = await make_priority(db, sort_order=1)
    high = await make_priority(db, sort_order=2)
    today = date.today()
    no_due = await make_task(db, user=user, priority_id=high.id)
    soon = await make_task(db, user=user, priority_id=low.id, due_date=today)
    later = await make_task(db, user=user, priority_id=high.id, due_date=today + timedelta(5))

    async def order(sort: str) -> list[int]:
        resp = await client.get("/api/tasks", params={"sort": sort})
        assert resp.status_code == 200, resp.text
        return [t["id"] for t in resp.json()["items"]]

    assert await order("due_date") == [soon.id, later.id, no_due.id]
    assert await order("-due_date") == [later.id, soon.id, no_due.id]
    assert await order("priority") == [later.id, no_due.id, soon.id]
    assert await order("-priority") == [soon.id, later.id, no_due.id]


async def test_pagination(client: AsyncClient, db: AsyncSession) -> None:
    user = await login_as(client, db)
    for _ in range(3):
        await make_task(db, user=user)
    body = (await client.get("/api/tasks", params={"limit": 2, "offset": 2})).json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 2
    assert len(body["items"]) == 1
