"""Import of the sheet's Data tab (POST /api/admin/import/data-tab).

tests/fixtures/data_tab_sample.csv is a trimmed copy of the owner's Data tab with the
same headers and the same quirks: projects listed under both enhancement categories
(one with different casing), activities shared by several groups, duplicate and
space-padded O&M projects, an empty "Project" column, and an O&M activity column that
names no project.
"""

from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Activity,
    ActivityGroup,
    ActivityGroupMember,
    Category,
    OmProject,
    Project,
    Role,
)
from tests.auth_helpers import login_as
from tests.factories import make_activity, make_activity_group, make_category, make_project

pytestmark = pytest.mark.anyio

URL = "/api/admin/import/data-tab"
SAMPLE = (Path(__file__).parent / "fixtures" / "data_tab_sample.csv").read_bytes()


async def _upload(client: AsyncClient, content: bytes = SAMPLE) -> Any:
    return await client.post(URL, files={"file": ("Data.csv", content, "text/csv")})


async def _project(db: AsyncSession, name: str) -> Project:
    project = await db.scalar(
        select(Project).where(func.lower(Project.name) == name.lower()),
        execution_options={"populate_existing": True},
    )
    assert project is not None, name
    return project


async def _group(db: AsyncSession, label: str) -> ActivityGroup:
    group = await db.scalar(
        select(ActivityGroup).where(ActivityGroup.label == label),
        execution_options={"populate_existing": True},
    )
    assert group is not None, label
    return group


async def _labels(db: AsyncSession, group: ActivityGroup) -> list[str]:
    rows = await db.scalars(
        select(Activity.label)
        .join(ActivityGroupMember)
        .where(ActivityGroupMember.activity_group_id == group.id)
        .order_by(ActivityGroupMember.sort_order)
    )
    return list(rows)


async def test_import_sample(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    resp = await _upload(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["created"] == {
        "categories": 4,
        "projects": 10,
        "activity_groups": 7,
        "activities": 12,
        "om_projects": 4,
    }
    assert body["linked"] == {
        "project_categories": 12,
        "project_groups": 10,
        "group_activities": 17,
        "om_flags": 1,
    }
    assert body["group_conflicts"] == []
    assert body["unlinked_groups"] == ["Operations & Maintenance _ Activity"]
    assert body["empty_columns"] == ["Project"]
    assert body["unrecognised_columns"] == []
    assert body["inactive_reused"] == []

    categories = {c.label: c for c in await db.scalars(select(Category))}
    assert list(categories) == [
        "Major Enhancements",
        "Minor Enhancements",
        "Operations & Maintenance",
        "Others",
    ]
    assert [c.requires_om_project for c in categories.values()] == [False, False, True, False]

    # Listed under both enhancement categories: one project, two links.
    shared = await _project(db, "Workforce Connect JSM")
    assert {c.label for c in shared.categories} == {"Major Enhancements", "Minor Enhancements"}
    tempo = await _project(db, "[Innov to SFA] Tempo DR")
    assert tempo.name == "[Innov to SFA] Tempo DR"  # first spelling wins
    assert len(tempo.categories) == 2

    project_activity = await _group(db, "Project_Activity")
    assert shared.activity_group_id == project_activity.id
    assert await _labels(db, project_activity) == [
        "Planning: Requirements Gathering",
        "Testing: UAT",
        "Analysis",
    ]
    admin_work = await _project(db, "Admin Work")
    assert admin_work.activity_group_id == (await _group(db, "Others_AdminWork")).id
    reflected = await _project(db, "Maintenance (Reflected in Service Desk)")
    not_reflected = await _project(db, "Maintenance (Not Reflected in Service Desk)")
    assert reflected.activity_group_id == (await _group(db, "OM_Reflected_Activity")).id
    assert not_reflected.activity_group_id == (await _group(db, "OM_Not_Reflected_Activity")).id

    # "Analysis" is one activity in four groups.
    analysis = await db.scalar(select(Activity).where(Activity.label == "Analysis"))
    assert analysis is not None
    in_groups = await db.scalar(
        select(func.count()).where(ActivityGroupMember.activity_id == analysis.id)
    )
    assert in_groups == 4
    unlinked = await _group(db, "Operations & Maintenance _ Activity")
    assert "Cut-off Support" in await _labels(db, unlinked)

    om_labels = list(await db.scalars(select(OmProject.label).order_by(OmProject.sort_order)))
    assert om_labels == [
        "[SFA-App] Collection",
        "Custom PR/PO",
        "FELCO Rewards App - Rewards Rebate",
        "Warehouse App",
    ]


async def test_import_is_idempotent(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    assert (await _upload(client)).status_code == 200
    counts = {
        model: await db.scalar(select(func.count()).select_from(model))
        for model in (Category, Project, Activity, ActivityGroup, ActivityGroupMember, OmProject)
    }

    body = (await _upload(client)).json()
    assert set(body["created"].values()) == {0}
    assert set(body["linked"].values()) == {0}
    assert body["group_conflicts"] == []
    for model, count in counts.items():
        assert await db.scalar(select(func.count()).select_from(model)) == count, model


async def test_import_reuses_existing_values(client: AsyncClient, db: AsyncSession) -> None:
    unrelated = await make_category(db, label="Development")
    major = await make_category(db, label="major enhancements")  # different casing
    analysis = await make_activity(db, label="ANALYSIS")
    custom_group = await make_activity_group(db, label="Warehouse activities")
    warehouse = await make_project(
        db, name="warehouse app", activity_group_id=custom_group.id, categories=[major]
    )
    hidden = await make_activity(db, label="Holidays", is_active=False)
    await login_as(client, db, role=Role.ADMIN)

    body = (await _upload(client)).json()

    assert body["created"]["categories"] == 3
    assert body["created"]["projects"] == 9
    assert body["created"]["activities"] == 10
    assert body["group_conflicts"] == [
        {
            "project": "warehouse app",
            "current_group": "Warehouse activities",
            "file_group": "Project_Activity",
        }
    ]
    assert body["inactive_reused"] == ["activity: Holidays"]

    await db.refresh(warehouse)
    assert warehouse.name == "warehouse app"  # never renamed
    assert warehouse.activity_group_id == custom_group.id  # kept
    await db.refresh(major)
    assert major.label == "major enhancements"
    await db.refresh(hidden)
    assert hidden.is_active is False
    await db.refresh(unrelated)
    assert unrelated.is_active is True  # not in the file: untouched, never deleted
    assert (
        await db.scalar(select(func.count()).where(func.lower(Activity.label) == "analysis")) == 1
    )
    group = await _group(db, "OM_Reflected_Activity")
    assert analysis.id in group.activity_ids


async def test_unrecognised_columns_reported(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    content = b"Others,Mystery_Column,Notes_\r\nAdmin Work,x,y\r\n"
    body = (await _upload(client, content)).json()
    assert body["unrecognised_columns"] == ["Mystery_Column", "Notes_"]
    assert body["created"]["projects"] == 1


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"Project_Activity\r\nTesting: UAT\r\n",  # no category column
        "Others\r\nAdmin Work\r\n".encode("utf-16"),
        b"Others\r\n" + b"x" * 101 + b"\r\n",  # project name too long
    ],
)
async def test_invalid_files_rejected(
    client: AsyncClient, db: AsyncSession, content: bytes
) -> None:
    await login_as(client, db, role=Role.ADMIN)
    resp = await _upload(client, content)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_file"
    assert await db.scalar(select(func.count()).select_from(Project)) == 0


@pytest.mark.parametrize("role", [Role.MANAGER, Role.DEV])
async def test_admin_only(client: AsyncClient, db: AsyncSession, role: Role) -> None:
    await login_as(client, db, role=role)
    assert (await _upload(client)).status_code == 403
