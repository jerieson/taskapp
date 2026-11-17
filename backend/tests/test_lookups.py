"""Dropdown values (categories, statuses, priorities, work set-ups, activities, activity
groups, O&M projects) and projects."""

import re

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Priority, Project, Role, Status
from tests.auth_helpers import login_as
from tests.factories import (
    make_activity,
    make_activity_group,
    make_category,
    make_om_project,
    make_priority,
    make_project,
    make_status,
    make_work_setup,
)

pytestmark = pytest.mark.anyio

PREFIXES = (
    "/api/categories",
    "/api/statuses",
    "/api/priorities",
    "/api/projects",
    "/api/work-setups",
    "/api/activities",
    "/api/activity-groups",
    "/api/om-projects",
)


def _routes(app: FastAPI) -> list[tuple[str, str]]:
    routes = []
    for path, ops in app.openapi()["paths"].items():
        if path.startswith(PREFIXES):
            concrete = re.sub(r"\{[^}]+\}", "1", path)
            routes.extend((method.upper(), concrete) for method in ops)
    return routes


async def _done_status(db: AsyncSession, **kw: object) -> Status:
    return await make_status(db, is_done=True, **kw)


# ---------------------------------------------------------------- access control


def test_no_delete_endpoints(app: FastAPI) -> None:
    methods = {method for method, _ in _routes(app)}
    assert "DELETE" not in methods
    assert {"GET", "POST", "PATCH", "PUT"} <= methods


@pytest.mark.parametrize("role", [Role.MANAGER, Role.DEV])
async def test_non_admin_cannot_write(
    app: FastAPI, client: AsyncClient, db: AsyncSession, role: Role
) -> None:
    await login_as(client, db, role=role)
    writes = [(m, p) for m, p in _routes(app) if m != "GET"]
    assert len(writes) >= 40
    for method, path in writes:
        resp = await client.request(method, path, json={"label": "x", "name": "x", "ids": [1]})
        assert resp.status_code == 403, (method, path, resp.status_code)


async def test_endpoints_require_login(app: FastAPI, client: AsyncClient) -> None:
    for method, path in _routes(app):
        if method == "GET":
            assert (await client.get(path)).status_code == 401, path


@pytest.mark.parametrize("prefix", PREFIXES)
async def test_non_admin_lists_active_only(
    client: AsyncClient, db: AsyncSession, prefix: str
) -> None:
    factory, field = {
        "/api/categories": (make_category, "label"),
        "/api/statuses": (make_status, "label"),
        "/api/priorities": (make_priority, "label"),
        "/api/projects": (make_project, "name"),
        "/api/work-setups": (make_work_setup, "label"),
        "/api/activities": (make_activity, "label"),
        "/api/activity-groups": (make_activity_group, "label"),
        "/api/om-projects": (make_om_project, "label"),
    }[prefix]
    active = await factory(db)
    inactive = await factory(db, is_active=False)
    await login_as(client, db, role=Role.DEV)

    resp = await client.get(prefix)
    assert resp.status_code == 200
    body = resp.json()
    values = [item[field] for item in body["items"]]
    assert getattr(active, field) in values
    assert getattr(inactive, field) not in values
    assert {"items", "total", "limit", "offset"} <= body.keys()

    resp = await client.get(prefix, params={"include_inactive": True})
    assert resp.status_code == 403


async def test_admin_can_list_inactive(client: AsyncClient, db: AsyncSession) -> None:
    hidden = await make_category(db, is_active=False)
    await login_as(client, db, role=Role.ADMIN)
    labels = [c["label"] for c in (await client.get("/api/categories")).json()["items"]]
    assert hidden.label not in labels
    resp = await client.get("/api/categories", params={"include_inactive": True})
    assert hidden.label in [c["label"] for c in resp.json()["items"]]


# ---------------------------------------------------------------- create / update


async def test_category_crud(client: AsyncClient, db: AsyncSession) -> None:
    existing = await make_category(db, sort_order=7)
    await login_as(client, db, role=Role.ADMIN)

    resp = await client.post("/api/categories", json={"label": " Ops ", "color": "#a1b2c3"})
    assert resp.status_code == 201, resp.text
    cat = resp.json()
    assert cat["label"] == "Ops"
    assert cat["color"] == "#A1B2C3"
    assert cat["sort_order"] == 8  # appended after the last
    assert cat["is_active"] is True

    resp = await client.post("/api/categories", json={"label": existing.label.upper()})
    assert resp.status_code == 409
    assert resp.json()["error"]["fields"]["label"]

    resp = await client.patch(f"/api/categories/{cat['id']}", json={"label": "Operations"})
    assert resp.json()["label"] == "Operations"
    assert resp.json()["color"] == "#A1B2C3"  # omitted: unchanged

    resp = await client.patch(f"/api/categories/{cat['id']}", json={"color": None})
    assert resp.json()["color"] is None

    resp = await client.patch(f"/api/categories/{cat['id']}", json={"color": "red"})
    assert resp.status_code == 422
    assert "color" in resp.json()["error"]["fields"]

    resp = await client.post(f"/api/categories/{cat['id']}/deactivate")
    assert resp.json()["is_active"] is False
    resp = await client.post(f"/api/categories/{cat['id']}/activate")
    assert resp.json()["is_active"] is True

    assert (await client.patch("/api/categories/999999", json={"label": "x"})).status_code == 404


async def test_first_status_becomes_default(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    first = (await client.post("/api/statuses", json={"label": "Open"})).json()
    second = (await client.post("/api/statuses", json={"label": "Closed", "is_done": True})).json()
    assert first["is_default"] is True
    assert second["is_default"] is False
    assert second["is_done"] is True


async def test_project_crud(client: AsyncClient, db: AsyncSession) -> None:
    await make_project(db, name="Apollo")
    await login_as(client, db, role=Role.ADMIN)

    resp = await client.post("/api/projects", json={"name": "Zephyr", "description": "  Wind  "})
    assert resp.status_code == 201, resp.text
    project = resp.json()
    assert project["description"] == "Wind"

    assert (await client.post("/api/projects", json={"name": "apollo"})).status_code == 409

    resp = await client.patch(f"/api/projects/{project['id']}", json={"name": "Zephyr 2"})
    assert resp.json()["name"] == "Zephyr 2"
    assert resp.json()["description"] == "Wind"

    resp = await client.post(f"/api/projects/{project['id']}/deactivate")
    assert resp.json()["is_active"] is False
    assert (await db.get(Project, project["id"])) is not None


# ---------------------------------------------------------------- defaults


@pytest.mark.parametrize("model", [Status, Priority])
async def test_default_cannot_be_deactivated(
    client: AsyncClient, db: AsyncSession, model: type[Status] | type[Priority]
) -> None:
    prefix = f"/api/{model.__tablename__}"
    factory = make_status if model is Status else make_priority
    default = await factory(db, is_default=True)
    await login_as(client, db, role=Role.ADMIN)

    resp = await client.post(f"{prefix}/{default.id}/deactivate")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "default_cannot_be_deactivated"
    await db.refresh(default)
    assert default.is_active
    assert default.is_default


@pytest.mark.parametrize("model", [Status, Priority])
async def test_set_default_leaves_exactly_one(
    client: AsyncClient, db: AsyncSession, model: type[Status] | type[Priority]
) -> None:
    prefix = f"/api/{model.__tablename__}"
    factory = make_status if model is Status else make_priority
    old = await factory(db, is_default=True)
    new = await factory(db)
    inactive = await factory(db, is_active=False)
    await login_as(client, db, role=Role.ADMIN)

    resp = await client.post(f"{prefix}/{new.id}/default")
    assert resp.status_code == 200
    assert resp.json()["is_default"] is True

    defaults = (await db.scalars(select(model).where(model.is_default))).all()
    assert [d.id for d in defaults] == [new.id]
    await db.refresh(old)
    assert old.is_default is False

    # Setting the current default again is a no-op.
    assert (await client.post(f"{prefix}/{new.id}/default")).status_code == 200
    assert await db.scalar(select(func.count()).where(model.is_default)) == 1

    # Inactive values cannot become the default.
    resp = await client.post(f"{prefix}/{inactive.id}/default")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "inactive_cannot_be_default"

    # The old default can now be deactivated.
    assert (await client.post(f"{prefix}/{old.id}/deactivate")).status_code == 200


async def test_categories_have_no_default_endpoint(client: AsyncClient, db: AsyncSession) -> None:
    cat = await make_category(db)
    await login_as(client, db, role=Role.ADMIN)
    assert (await client.post(f"/api/categories/{cat.id}/default")).status_code in (404, 405)


# ---------------------------------------------------------------- done statuses


async def test_last_done_status_cannot_be_deactivated(
    client: AsyncClient, db: AsyncSession
) -> None:
    done = await _done_status(db)
    await make_status(db, is_done=True, is_active=False)  # inactive ones don't count
    await login_as(client, db, role=Role.ADMIN)

    resp = await client.post(f"/api/statuses/{done.id}/deactivate")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "last_done_status"


async def test_last_done_status_cannot_be_unmarked(client: AsyncClient, db: AsyncSession) -> None:
    done = await _done_status(db)
    await login_as(client, db, role=Role.ADMIN)

    resp = await client.patch(f"/api/statuses/{done.id}", json={"is_done": False})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "last_done_status"
    await db.refresh(done)
    assert done.is_done is True


async def test_done_status_removable_when_another_exists(
    client: AsyncClient, db: AsyncSession
) -> None:
    first = await _done_status(db)
    second = await _done_status(db)
    await login_as(client, db, role=Role.ADMIN)

    resp = await client.patch(f"/api/statuses/{first.id}", json={"is_done": False})
    assert resp.status_code == 200
    assert resp.json()["is_done"] is False

    # `second` is now the only active done status.
    assert (await client.post(f"/api/statuses/{second.id}/deactivate")).status_code == 409
    resp = await client.patch(f"/api/statuses/{first.id}", json={"is_done": True})
    assert resp.json()["is_done"] is True
    assert (await client.post(f"/api/statuses/{second.id}/deactivate")).status_code == 200


# ---------------------------------------------------------------- reorder


async def test_reorder(client: AsyncClient, db: AsyncSession) -> None:
    a = await make_category(db, sort_order=1)
    b = await make_category(db, sort_order=2)
    c = await make_category(db, sort_order=3, is_active=False)
    await login_as(client, db, role=Role.ADMIN)

    resp = await client.put("/api/categories/order", json={"ids": [c.id, a.id, b.id]})
    assert resp.status_code == 204
    resp = await client.get("/api/categories", params={"include_inactive": True})
    assert [item["id"] for item in resp.json()["items"]] == [c.id, a.id, b.id]
    rows = await db.scalars(select(Category).order_by(Category.sort_order))
    assert [r.sort_order for r in rows] == [1, 2, 3]


@pytest.mark.parametrize("ids", ["missing", "duplicate", "unknown"])
async def test_reorder_requires_every_id_once(
    client: AsyncClient, db: AsyncSession, ids: str
) -> None:
    a = await make_priority(db, sort_order=1)
    b = await make_priority(db, sort_order=2)
    await login_as(client, db, role=Role.ADMIN)
    body = {"missing": [a.id], "duplicate": [a.id, a.id, b.id], "unknown": [a.id, b.id, 999999]}
    resp = await client.put("/api/priorities/order", json={"ids": body[ids]})
    assert resp.status_code == 422
    assert "ids" in resp.json()["error"]["fields"]
