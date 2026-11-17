"""Processes and runs: ownership, steps, run creation, template independence,
auto-complete/reopen, cancel, delete rules."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Priority, Process, ProcessRun, ProcessStep, Role, RunStatus, Status, Task
from tests.auth_helpers import login_as
from tests.factories import make_category, make_priority, make_status

pytestmark = pytest.mark.anyio


async def _defaults(db: AsyncSession) -> tuple[Status, Priority]:
    """Fresh default status and priority (any existing default loses the flag)."""
    for model in (Status, Priority):
        for row in await db.scalars(select(model).where(model.is_default)):
            row.is_default = False
    await db.flush()
    return await make_status(db, is_default=True), await make_priority(db, is_default=True)


async def _create(client: AsyncClient, steps: list[dict] | None = None, **kw: object) -> dict:
    if steps is None:
        steps = [{"title": "Step A"}, {"title": "Step B", "description": "Do B"}]
    resp = await client.post("/api/processes", json={"name": "Release", "steps": steps, **kw})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _start(client: AsyncClient, process_id: int, **kw: object) -> dict:
    resp = await client.post(f"/api/processes/{process_id}/runs", json=kw)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _set_status(client: AsyncClient, task_id: int, status: Status) -> None:
    resp = await client.patch(f"/api/tasks/{task_id}", json={"status_id": status.id})
    assert resp.status_code == 200, resp.text


async def _run(client: AsyncClient, run_id: int) -> dict:
    resp = await client.get(f"/api/runs/{run_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------- access control


async def test_endpoints_require_login(client: AsyncClient) -> None:
    assert (await client.get("/api/processes")).status_code == 401
    assert (await client.get("/api/processes/1")).status_code == 401
    assert (await client.get("/api/runs/1")).status_code == 401


@pytest.mark.parametrize("role", [Role.ADMIN, Role.MANAGER, Role.DEV])
async def test_another_users_process_and_run_are_404(
    client: AsyncClient, new_client, db: AsyncSession, role: Role
) -> None:
    await _defaults(db)
    owner_client = new_client()
    owner = await login_as(owner_client, db)
    process = await _create(owner_client)
    run = await _start(owner_client, process["id"])
    step_id = process["steps"][0]["id"]

    me = await login_as(client, db, role=role)
    if role != Role.ADMIN:
        # Even a teammate (or their manager) cannot see it.
        owner.team_id = me.team_id
        await db.flush()

    base = f"/api/processes/{process['id']}"
    assert (await client.get(base)).status_code == 404
    assert (await client.patch(base, json={"name": "Mine"})).status_code == 404
    assert (await client.delete(base)).status_code == 404
    assert (await client.post(f"{base}/deactivate")).status_code == 404
    assert (await client.post(f"{base}/steps", json={"title": "X"})).status_code == 404
    assert (await client.put(f"{base}/steps", json={"steps": []})).status_code == 404
    order = await client.put(f"{base}/steps/order", json={"step_ids": [step_id]})
    assert order.status_code == 404
    assert (await client.patch(f"{base}/steps/{step_id}", json={"title": "X"})).status_code == 404
    assert (await client.delete(f"{base}/steps/{step_id}")).status_code == 404
    assert (await client.get(f"{base}/runs")).status_code == 404
    assert (await client.post(f"{base}/runs", json={})).status_code == 404
    assert (await client.get(f"/api/runs/{run['id']}")).status_code == 404
    assert (await client.post(f"/api/runs/{run['id']}/cancel")).status_code == 404
    assert (await client.get("/api/processes")).json()["total"] == 0
    # Nothing changed for the owner.
    assert (await _run(owner_client, run["id"]))["status"] == "in_progress"
    assert len((await owner_client.get(base)).json()["steps"]) == 2


async def test_step_of_another_process_is_404(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    first = await _create(client)
    second = await _create(client)
    other_step = second["steps"][0]["id"]
    url = f"/api/processes/{first['id']}/steps/{other_step}"
    assert (await client.patch(url, json={"title": "X"})).status_code == 404
    assert (await client.delete(url)).status_code == 404


# ---------------------------------------------------------------- processes and steps


async def test_create_with_steps_and_list(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    category = await make_category(db)
    process = await _create(
        client,
        steps=[
            {"title": "  Plan  ", "default_category_id": category.id, "estimated_hours": 1.5},
            {"title": "Ship"},
        ],
        description="",
    )
    assert process["name"] == "Release"
    assert process["description"] is None
    assert process["is_active"] is True
    assert [s["title"] for s in process["steps"]] == ["Plan", "Ship"]
    assert [s["step_order"] for s in process["steps"]] == [0, 1]
    assert process["steps"][0]["default_category"]["id"] == category.id
    assert process["steps"][0]["estimated_hours"] == 1.5
    assert (process["step_count"], process["run_count"]) == (2, 0)

    listed = (await client.get("/api/processes")).json()
    assert listed["total"] == 1
    assert listed["items"][0]["step_count"] == 2


async def test_inactive_category_rejected_on_new_step_but_kept(
    client: AsyncClient, db: AsyncSession
) -> None:
    await login_as(client, db)
    inactive = await make_category(db, is_active=False)
    resp = await client.post(
        "/api/processes",
        json={"name": "P", "steps": [{"title": "A", "default_category_id": inactive.id}]},
    )
    assert resp.status_code == 422
    assert "steps.0.default_category_id" in resp.json()["error"]["fields"]

    category = await make_category(db)
    process = await _create(client, steps=[{"title": "A", "default_category_id": category.id}])
    category.is_active = False
    await db.flush()
    step = process["steps"][0]
    url = f"/api/processes/{process['id']}/steps/{step['id']}"
    # Keeping the now-inactive category is fine; choosing it anew is not.
    resp = await client.patch(url, json={"title": "Renamed", "default_category_id": category.id})
    assert resp.status_code == 200, resp.text
    add = await client.post(
        f"/api/processes/{process['id']}/steps",
        json={"title": "B", "default_category_id": category.id},
    )
    assert add.status_code == 422


async def test_step_add_update_delete_reorder(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    process = await _create(client)
    base = f"/api/processes/{process['id']}"
    a, b = (s["id"] for s in process["steps"])

    resp = await client.post(f"{base}/steps", json={"title": "Step C"})
    assert resp.status_code == 201
    c = resp.json()["steps"][2]["id"]

    resp = await client.patch(f"{base}/steps/{b}", json={"description": None})
    assert resp.json()["steps"][1]["description"] is None
    assert (await client.patch(f"{base}/steps/{b}", json={"title": None})).status_code == 422

    resp = await client.put(f"{base}/steps/order", json={"step_ids": [c, a, b]})
    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()["steps"]] == [c, a, b]
    assert [s["step_order"] for s in resp.json()["steps"]] == [0, 1, 2]
    bad = await client.put(f"{base}/steps/order", json={"step_ids": [c, a]})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "invalid_order"

    assert (await client.delete(f"{base}/steps/{a}")).status_code == 204
    steps = (await client.get(base)).json()["steps"]
    assert [s["id"] for s in steps] == [c, b]
    assert [s["step_order"] for s in steps] == [0, 1]


async def test_sync_steps(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    process = await _create(client)
    base = f"/api/processes/{process['id']}"
    a, b = (s["id"] for s in process["steps"])

    resp = await client.put(
        f"{base}/steps",
        json={"steps": [{"title": "New first"}, {"id": b, "title": "B renamed"}]},
    )
    assert resp.status_code == 200, resp.text
    steps = resp.json()["steps"]
    assert [s["title"] for s in steps] == ["New first", "B renamed"]
    assert steps[1]["id"] == b
    assert await db.get(ProcessStep, a) is None

    unknown = await client.put(f"{base}/steps", json={"steps": [{"id": a, "title": "Gone"}]})
    assert unknown.status_code == 422
    assert "steps.0.id" in unknown.json()["error"]["fields"]
    dup = await client.put(
        f"{base}/steps", json={"steps": [{"id": b, "title": "X"}, {"id": b, "title": "Y"}]}
    )
    assert dup.status_code == 422


async def test_update_and_deactivate(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    process = await _create(client)
    base = f"/api/processes/{process['id']}"
    resp = await client.patch(base, json={"name": "Renamed", "description": "Why"})
    assert (resp.json()["name"], resp.json()["description"]) == ("Renamed", "Why")
    assert (await client.patch(base, json={"name": None})).status_code == 422

    assert (await client.post(f"{base}/deactivate")).json()["is_active"] is False
    assert (await client.get("/api/processes?is_active=true")).json()["total"] == 0
    assert (await client.get("/api/processes?is_active=false")).json()["total"] == 1
    assert (await client.post(f"{base}/activate")).json()["is_active"] is True


async def test_delete_process(client: AsyncClient, db: AsyncSession) -> None:
    await _defaults(db)
    await login_as(client, db)
    unused = await _create(client)
    assert (await client.delete(f"/api/processes/{unused['id']}")).status_code == 204
    assert await db.get(Process, unused["id"]) is None
    remaining_steps = await db.scalar(
        select(func.count()).where(ProcessStep.process_id == unused["id"])
    )
    assert remaining_steps == 0

    used = await _create(client)
    run = await _start(client, used["id"])
    # Cancelling the run does not make the process deletable.
    await client.post(f"/api/runs/{run['id']}/cancel")
    resp = await client.delete(f"/api/processes/{used['id']}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "process_has_runs"
    assert await db.get(Process, used["id"]) is not None


# ---------------------------------------------------------------- runs


async def test_start_run_copies_steps_into_tasks(client: AsyncClient, db: AsyncSession) -> None:
    status, priority = await _defaults(db)
    me = await login_as(client, db)
    category = await make_category(db)
    retired = await make_category(db)
    process = await _create(
        client,
        steps=[
            {"title": "Plan", "description": "Write it", "default_category_id": category.id},
            {"title": "Ship", "default_category_id": retired.id},
        ],
    )
    retired.is_active = False
    await db.flush()

    run = await _start(client, process["id"], due_date="2026-12-01")
    assert run["status"] == "in_progress"
    assert run["process"] == {"id": process["id"], "name": "Release", "is_active": True}
    assert run["progress"] == {"done": 0, "total": 2}
    plan, ship = run["tasks"]
    assert (plan["title"], plan["description"]) == ("Plan", "Write it")
    assert plan["category"]["id"] == category.id
    assert ship["category"] is None  # deactivated since the step was saved
    for task, step in zip(run["tasks"], process["steps"], strict=True):
        assert task["status"]["id"] == status.id
        assert task["priority"]["id"] == priority.id
        assert task["due_date"] == "2026-12-01"
        assert task["process_run_id"] == run["id"]
        assert task["process_step_id"] == step["id"]
        assert task["completed_at"] is None

    # They are ordinary tasks of the caller.
    owned = await db.scalar(select(func.count()).where(Task.user_id == me.id))
    assert owned == 2
    listed = (await client.get(f"/api/tasks?process_run_id={run['id']}")).json()
    assert listed["total"] == 2

    runs = (await client.get(f"/api/processes/{process['id']}/runs")).json()
    assert runs["total"] == 1
    assert runs["items"][0]["progress"] == {"done": 0, "total": 2}
    detail = (await client.get(f"/api/processes/{process['id']}")).json()
    assert (detail["run_count"], detail["active_run_count"]) == (1, 1)


async def test_cannot_start_run_on_inactive_or_empty_process(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _defaults(db)
    await login_as(client, db)
    empty = await _create(client, steps=[])
    resp = await client.post(f"/api/processes/{empty['id']}/runs", json={})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "process_has_no_steps"

    process = await _create(client)
    await client.post(f"/api/processes/{process['id']}/deactivate")
    resp = await client.post(f"/api/processes/{process['id']}/runs", json={})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "process_inactive"
    assert await db.scalar(select(func.count()).select_from(ProcessRun)) == 0


async def test_start_run_without_default_status_creates_nothing(
    client: AsyncClient, db: AsyncSession
) -> None:
    for row in await db.scalars(select(Status).where(Status.is_default)):
        row.is_default = False
    await db.flush()
    me = await login_as(client, db)
    process = await _create(client)
    resp = await client.post(f"/api/processes/{process['id']}/runs", json={})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "no_default_status"
    assert await db.scalar(select(func.count()).where(Task.user_id == me.id)) == 0


async def test_editing_template_does_not_change_existing_run(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _defaults(db)
    await login_as(client, db)
    category = await make_category(db)
    process = await _create(client)
    base = f"/api/processes/{process['id']}"
    a, b = (s["id"] for s in process["steps"])
    run = await _start(client, process["id"])
    before = {t["id"]: (t["title"], t["description"], t["category"]) for t in run["tasks"]}

    await client.patch(
        f"{base}/steps/{a}",
        json={"title": "Changed", "description": "New", "default_category_id": category.id},
    )
    await client.post(f"{base}/steps", json={"title": "Extra"})
    assert (await client.delete(f"{base}/steps/{b}")).status_code == 204
    await client.put(f"{base}/steps", json={"steps": [{"title": "Totally new"}]})

    after = await _run(client, run["id"])
    assert {t["id"]: (t["title"], t["description"], t["category"]) for t in after["tasks"]} == (
        before
    )
    # The deleted steps' tasks stay, only losing the link to the step.
    assert [t["process_step_id"] for t in after["tasks"]] == [None, None]
    assert after["progress"]["total"] == 2


async def test_run_completes_and_reopens_with_its_tasks(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _defaults(db)
    await login_as(client, db)
    done = await make_status(db, is_done=True)
    also_done = await make_status(db, is_done=True)
    open_status = await make_status(db)
    process = await _create(client)
    run = await _start(client, process["id"])
    first, second = (t["id"] for t in run["tasks"])

    await _set_status(client, first, done)
    state = await _run(client, run["id"])
    assert state["status"] == "in_progress"
    assert state["progress"] == {"done": 1, "total": 2}

    await _set_status(client, second, done)
    state = await _run(client, run["id"])
    assert state["status"] == "completed"
    assert state["completed_at"] is not None
    assert state["progress"] == {"done": 2, "total": 2}
    detail = (await client.get(f"/api/processes/{process['id']}")).json()
    assert detail["active_run_count"] == 0

    # Moving between done statuses keeps it completed.
    await _set_status(client, second, also_done)
    assert (await _run(client, run["id"]))["status"] == "completed"

    await _set_status(client, first, open_status)
    state = await _run(client, run["id"])
    assert state["status"] == "in_progress"
    assert state["completed_at"] is None

    # Deleting the last open task completes the run.
    assert (await client.delete(f"/api/tasks/{first}")).status_code == 204
    state = await _run(client, run["id"])
    assert state["status"] == "completed"
    assert state["progress"] == {"done": 1, "total": 1}


async def test_cancel_keeps_tasks_and_stays_cancelled(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _defaults(db)
    await login_as(client, db)
    done = await make_status(db, is_done=True)
    process = await _create(client)
    run = await _start(client, process["id"])

    resp = await client.post(f"/api/runs/{run['id']}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert len(resp.json()["tasks"]) == 2

    for task in run["tasks"]:
        await _set_status(client, task["id"], done)
    assert (await _run(client, run["id"]))["status"] == "cancelled"

    again = await client.post(f"/api/runs/{run['id']}/cancel")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "run_not_in_progress"
    stored = await db.get(ProcessRun, run["id"], populate_existing=True)
    assert stored is not None
    assert stored.status == RunStatus.CANCELLED


async def test_runs_list_filter_and_order(client: AsyncClient, db: AsyncSession) -> None:
    await _defaults(db)
    await login_as(client, db)
    process = await _create(client)
    older = await _start(client, process["id"])
    newer = await _start(client, process["id"])
    await client.post(f"/api/runs/{older['id']}/cancel")

    url = f"/api/processes/{process['id']}/runs"
    listed = (await client.get(url)).json()["items"]
    assert [r["id"] for r in listed] == [newer["id"], older["id"]]
    cancelled = (await client.get(f"{url}?status=cancelled")).json()
    assert [r["id"] for r in cancelled["items"]] == [older["id"]]
