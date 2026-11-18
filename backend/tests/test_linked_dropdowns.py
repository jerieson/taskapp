"""Linked dropdowns: work set-ups, activities, activity groups, O&M projects, project
links (categories + activity group) and the log form's options."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role, WorkSetup
from tests.auth_helpers import login_as
from tests.factories import (
    make_activity,
    make_activity_group,
    make_category,
    make_om_project,
    make_project,
)

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------- work set-ups


async def test_work_setups_seeded_with_one_default(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.DEV)
    items = (await client.get("/api/work-setups")).json()["items"]
    assert len(items) == 3
    assert sum(item["is_default"] for item in items) == 1
    # On-Site is the default (owner's correction after checking the sheet).
    assert [item["label"] for item in items if item["is_default"]] == ["On-Site"]


async def test_work_setup_default_rules(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    default = await db.scalar(select(WorkSetup).where(WorkSetup.is_default))
    assert default is not None

    resp = await client.post(f"/api/work-setups/{default.id}/deactivate")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "default_cannot_be_deactivated"

    new = (await client.post("/api/work-setups", json={"label": "Hybrid"})).json()
    assert new["is_default"] is False  # a default already exists
    assert (await client.post(f"/api/work-setups/{new['id']}/default")).status_code == 200

    defaults = (await db.scalars(select(WorkSetup).where(WorkSetup.is_default))).all()
    assert [row.id for row in defaults] == [new["id"]]
    assert (await client.post(f"/api/work-setups/{default.id}/deactivate")).status_code == 200


# ---------------------------------------------------------------- activities / O&M projects


async def test_activity_and_om_project_crud(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    long_label = "Testing: System Integration Testing (SIT) for the whole release train"
    resp = await client.post("/api/activities", json={"label": long_label, "color": "#00aa00"})
    assert resp.status_code == 201, resp.text
    activity = resp.json()
    assert activity["label"] == long_label  # activities allow up to 100 characters
    assert activity["color"] == "#00AA00"
    resp = await client.post("/api/activities", json={"label": long_label.upper()})
    assert resp.status_code == 409

    resp = await client.post("/api/om-projects", json={"label": " [SFA-App] Collection "})
    assert resp.status_code == 201, resp.text
    om = resp.json()
    assert om["label"] == "[SFA-App] Collection"
    assert "color" not in om
    resp = await client.patch(f"/api/om-projects/{om['id']}", json={"label": "Collection"})
    assert resp.json()["label"] == "Collection"
    assert (await client.post(f"/api/om-projects/{om['id']}/deactivate")).json()[
        "is_active"
    ] is False


async def test_category_om_flag(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    resp = await client.post("/api/categories", json={"label": "O&M", "requires_om_project": True})
    assert resp.status_code == 201, resp.text
    category = resp.json()
    assert category["requires_om_project"] is True
    resp = await client.patch(f"/api/categories/{category['id']}", json={"label": "Ops"})
    assert resp.json()["requires_om_project"] is True  # omitted: unchanged
    resp = await client.patch(
        f"/api/categories/{category['id']}", json={"requires_om_project": False}
    )
    assert resp.json()["requires_om_project"] is False


# ---------------------------------------------------------------- activity groups


async def test_group_members_replace_in_order(client: AsyncClient, db: AsyncSession) -> None:
    a = await make_activity(db)
    b = await make_activity(db)
    c = await make_activity(db)
    await login_as(client, db, role=Role.ADMIN)

    group = (await client.post("/api/activity-groups", json={"label": "Project_Activity"})).json()
    assert group["activity_ids"] == []

    url = f"/api/activity-groups/{group['id']}/activities"
    resp = await client.put(url, json={"activity_ids": [c.id, a.id]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["activity_ids"] == [c.id, a.id]

    resp = await client.put(url, json={"activity_ids": [a.id, b.id, c.id]})
    assert resp.json()["activity_ids"] == [a.id, b.id, c.id]

    listed = (await client.get("/api/activity-groups")).json()["items"]
    assert next(g for g in listed if g["id"] == group["id"])["activity_ids"] == [a.id, b.id, c.id]

    resp = await client.put(url, json={"activity_ids": [b.id]})
    assert resp.json()["activity_ids"] == [b.id]


async def test_activity_shared_by_groups(client: AsyncClient, db: AsyncSession) -> None:
    shared = await make_activity(db)
    first = await make_activity_group(db, activities=[shared])
    second = await make_activity_group(db)
    await login_as(client, db, role=Role.ADMIN)

    resp = await client.put(
        f"/api/activity-groups/{second.id}/activities", json={"activity_ids": [shared.id]}
    )
    assert resp.json()["activity_ids"] == [shared.id]
    resp = await client.get("/api/activity-groups")
    by_id = {g["id"]: g["activity_ids"] for g in resp.json()["items"]}
    assert by_id[first.id] == [shared.id]
    assert by_id[second.id] == [shared.id]


async def test_group_members_validation(client: AsyncClient, db: AsyncSession) -> None:
    kept = await make_activity(db)
    group = await make_activity_group(db, activities=[kept])
    kept.is_active = False
    inactive = await make_activity(db, is_active=False)
    await db.flush()
    await login_as(client, db, role=Role.ADMIN)
    url = f"/api/activity-groups/{group.id}/activities"

    # An inactive member may stay; a new inactive or unknown one is rejected.
    assert (await client.put(url, json={"activity_ids": [kept.id]})).status_code == 200
    for ids in ([kept.id, inactive.id], [999999]):
        resp = await client.put(url, json={"activity_ids": ids})
        assert resp.status_code == 422
        assert "activity_ids" in resp.json()["error"]["fields"]
    resp = await client.put(url, json={"activity_ids": [kept.id, kept.id]})
    assert resp.status_code == 422
    assert (
        await client.put("/api/activity-groups/999999/activities", json={"activity_ids": []})
    ).status_code == 404


# ---------------------------------------------------------------- projects


async def test_project_links(client: AsyncClient, db: AsyncSession) -> None:
    major = await make_category(db, sort_order=1)
    minor = await make_category(db, sort_order=2)
    group = await make_activity_group(db)
    other_group = await make_activity_group(db)
    await login_as(client, db, role=Role.ADMIN)

    resp = await client.post(
        "/api/projects",
        json={"name": "Warehouse App", "category_ids": [minor.id], "activity_group_id": group.id},
    )
    assert resp.status_code == 201, resp.text
    project = resp.json()
    assert project["category_ids"] == [minor.id]
    assert project["activity_group_id"] == group.id

    url = f"/api/projects/{project['id']}"
    resp = await client.patch(url, json={"category_ids": [minor.id, major.id]})
    assert sorted(resp.json()["category_ids"]) == sorted([major.id, minor.id])
    assert resp.json()["activity_group_id"] == group.id  # omitted: unchanged

    resp = await client.patch(url, json={"activity_group_id": other_group.id})
    assert resp.json()["activity_group_id"] == other_group.id
    resp = await client.patch(url, json={"activity_group_id": None, "category_ids": []})
    assert resp.json()["activity_group_id"] is None
    assert resp.json()["category_ids"] == []


async def test_project_links_validation(client: AsyncClient, db: AsyncSession) -> None:
    inactive_category = await make_category(db, is_active=False)
    inactive_group = await make_activity_group(db, is_active=False)
    await login_as(client, db, role=Role.ADMIN)

    for body, field in [
        ({"category_ids": [inactive_category.id]}, "category_ids"),
        ({"category_ids": [999999]}, "category_ids"),
        ({"activity_group_id": inactive_group.id}, "activity_group_id"),
        ({"activity_group_id": 999999}, "activity_group_id"),
    ]:
        resp = await client.post("/api/projects", json={"name": "P", **body})
        assert resp.status_code == 422, body
        assert field in resp.json()["error"]["fields"]

    # Inactive links already on a project may stay.
    project = await make_project(
        db, activity_group_id=inactive_group.id, categories=[inactive_category]
    )
    resp = await client.patch(
        f"/api/projects/{project.id}",
        json={"category_ids": [inactive_category.id], "activity_group_id": inactive_group.id},
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------- log options


async def test_log_options(client: AsyncClient, db: AsyncSession) -> None:
    om_category = await make_category(db, requires_om_project=True)
    inactive_category = await make_category(db, is_active=False)
    active_activity = await make_activity(db)
    inactive_activity = await make_activity(db, is_active=False)
    group = await make_activity_group(db, activities=[inactive_activity, active_activity])
    inactive_group = await make_activity_group(db, is_active=False)
    project = await make_project(
        db, activity_group_id=group.id, categories=[om_category, inactive_category]
    )
    orphan = await make_project(db, activity_group_id=inactive_group.id)
    hidden_project = await make_project(db, is_active=False)
    om = await make_om_project(db)
    hidden_om = await make_om_project(db, is_active=False)

    await login_as(client, db, role=Role.DEV)
    resp = await client.get("/api/log-options")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert [c["id"] for c in body["categories"]] == [om_category.id]
    assert body["categories"][0]["requires_om_project"] is True
    projects = {p["id"]: p for p in body["projects"]}
    assert hidden_project.id not in projects
    assert projects[project.id]["category_ids"] == [om_category.id]
    assert projects[project.id]["activity_group_id"] == group.id
    assert projects[orphan.id]["activity_group_id"] is None
    groups = {g["id"]: g for g in body["activity_groups"]}
    assert inactive_group.id not in groups
    assert groups[group.id]["activity_ids"] == [active_activity.id]
    assert [a["id"] for a in body["activities"]] == [active_activity.id]
    om_ids = [o["id"] for o in body["om_projects"]]
    assert om.id in om_ids
    assert hidden_om.id not in om_ids
    assert sum(w["is_default"] for w in body["work_setups"]) == 1


async def test_log_options_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/api/log-options")).status_code == 401
