"""Prod log export: CSV in the sheet's column order, scoping, Excel safety."""

import csv
import io
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role
from tests.auth_helpers import login_as
from tests.factories import (
    make_deviation_reason,
    make_linked,
    make_log,
    make_om_project,
    make_team,
    make_user,
)

pytestmark = pytest.mark.anyio

NOV_3 = date(2026, 11, 3)
RANGE = {"date_from": "2026-11-01", "date_to": "2026-11-30"}


async def _export(client: AsyncClient, **params: object) -> Response:
    return await client.get("/api/logs/export", params={**RANGE, **params})


def _rows(resp: Response) -> list[list[str]]:
    assert resp.status_code == 200, resp.text
    assert resp.content.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM"
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))


async def test_columns_and_formats(client: AsyncClient, db: AsyncSession) -> None:
    user = await login_as(client, db, username="ana")
    refs = await make_linked(db, label="Operations & Maintenance", requires_om_project=True)
    om = await make_om_project(db, label="[SFA-App] Collection")
    reason = await make_deviation_reason(db, label="Scope Creep (test)")
    await make_log(
        db,
        user=user,
        log_date=NOV_3,
        planned_hours=Decimal("0.1"),
        hours_spent=Decimal("2.65"),
        is_planned=True,
        om_project_id=om.id,
        deviation_reason_id=reason.id,
        description="With the client",
        created_at=datetime(2026, 11, 2, 23, 0, tzinfo=UTC),
        **refs.ids(),
    )
    await make_log(
        db,
        user=user,
        log_date=date(2026, 11, 4),
        hours_spent=Decimal(1),
        is_planned=False,
        description=None,
        **refs.ids(),
    )

    resp = await _export(client)
    assert resp.headers["content-type"].startswith("text/csv")
    assert "ana_2026-11-01_2026-11-30_productivity_log.csv" in resp.headers["content-disposition"]
    header, first, second = _rows(resp)
    assert header == [
        "Date",
        "Work Set-Up",
        "Planned Hours",
        "Actual Hours Consumed",
        "Planned",
        "Category",
        "Project",
        "Activity/Task",
        "Project (For O&M)",
        "Reason for Deviation",
        "Remarks",
        "Date Created",
    ]
    assert first == [
        "3-Nov-2026",
        "On-Site",
        "0.10",
        "2.65",
        "Planned",
        "Operations & Maintenance",
        refs.project.name,
        refs.activity.label,
        "[SFA-App] Collection",
        "Scope Creep (test)",
        "With the client",
        "2-Nov-2026",
    ]
    assert second[:5] == ["4-Nov-2026", "On-Site", "", "1.00", "Unplanned"]
    assert second[8:11] == ["", "", ""]


async def test_date_created_uses_app_timezone(
    client: AsyncClient, db: AsyncSession, settings_override: object
) -> None:
    settings_override(app_timezone="Asia/Manila")  # type: ignore[operator]
    user = await login_as(client, db)
    await make_log(
        db, user=user, log_date=NOV_3, created_at=datetime(2026, 11, 2, 18, 0, tzinfo=UTC)
    )
    assert _rows(await _export(client))[1][-1] == "3-Nov-2026"


async def test_sorted_by_date_then_creation_and_range(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await login_as(client, db)
    t = datetime(2026, 11, 1, tzinfo=UTC)
    await make_log(db, user=user, log_date=date(2026, 11, 5), description="c", created_at=t)
    await make_log(db, user=user, log_date=NOV_3, description="b", created_at=t.replace(hour=5))
    await make_log(db, user=user, log_date=NOV_3, description="a", created_at=t)
    await make_log(db, user=user, log_date=date(2026, 12, 1), description="out of range")
    await make_log(db, user=user, log_date=date(2026, 10, 31), description="out of range")
    rows = _rows(await _export(client))
    assert [r[10] for r in rows[1:]] == ["a", "b", "c"]


async def test_formula_injection_escaped(client: AsyncClient, db: AsyncSession) -> None:
    user = await login_as(client, db)
    for i, text in enumerate(["=SUM(A1)", "+1", "-2", "@cmd", "\tx", "plain = ok"]):
        await make_log(
            db,
            user=user,
            log_date=NOV_3,
            description=text,
            created_at=datetime(2026, 11, 1, i, tzinfo=UTC),
        )
    rows = _rows(await _export(client))
    assert [r[10] for r in rows[1:]] == ["'=SUM(A1)", "'+1", "'-2", "'@cmd", "'\tx", "plain = ok"]


async def test_empty_export_has_header(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    rows = _rows(await _export(client))
    assert len(rows) == 1


async def test_dev_cannot_export_others(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    teammate = await make_user(db, team_id=me.team_id)
    await make_log(db, user=teammate, log_date=NOV_3)
    assert (await _export(client, user_id=teammate.id)).status_code == 404
    assert (await _export(client, user_id=999_999)).status_code == 404
    assert len(_rows(await _export(client, user_id=me.id))) == 1


async def test_manager_exports_team_snapshot_only(client: AsyncClient, db: AsyncSession) -> None:
    team = await make_team(db)
    other = await make_team(db)
    await login_as(client, db, Role.MANAGER, team=team)
    member = await make_user(db, team=team)
    await make_log(db, user=member, log_date=NOV_3, description="in team")
    # Written while in another team: stays out of this manager's export.
    await make_log(db, user=member, log_date=NOV_3, team_id=other.id, description="elsewhere")
    rows = _rows(await _export(client, user_id=member.id))
    assert [r[10] for r in rows[1:]] == ["in team"]


async def test_manager_former_member_and_outsiders(client: AsyncClient, db: AsyncSession) -> None:
    team = await make_team(db)
    other = await make_team(db)
    await login_as(client, db, Role.MANAGER, team=team)
    moved = await make_user(db, team=other)
    await make_log(db, user=moved, log_date=NOV_3, team_id=team.id, description="before move")
    await make_log(db, user=moved, log_date=NOV_3, description="after move")
    rows = _rows(await _export(client, user_id=moved.id))
    assert [r[10] for r in rows[1:]] == ["before move"]

    outsider = await make_user(db, team=other)
    await make_log(db, user=outsider, log_date=NOV_3)
    assert (await _export(client, user_id=outsider.id)).status_code == 404


async def test_admin_exports_anyone(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, Role.ADMIN)
    team, other = await make_team(db), await make_team(db)
    user = await make_user(db, team=team, is_active=False)
    await make_log(db, user=user, log_date=NOV_3, description="a")
    await make_log(db, user=user, log_date=NOV_3, team_id=other.id, description="b")
    rows = _rows(await _export(client, user_id=user.id))
    assert sorted(r[10] for r in rows[1:]) == ["a", "b"]
    assert (await _export(client, user_id=999_999)).status_code == 404


async def test_validation(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    bad = await client.get(
        "/api/logs/export", params={"date_from": "2026-11-30", "date_to": "2026-11-01"}
    )
    assert bad.status_code == 422
    too_long = await client.get(
        "/api/logs/export", params={"date_from": "2025-01-01", "date_to": "2026-11-01"}
    )
    assert too_long.status_code == 422
    missing = await client.get("/api/logs/export", params={"date_from": "2026-11-01"})
    assert missing.status_code == 422


async def test_requires_login(client: AsyncClient) -> None:
    assert (await _export(client)).status_code == 401


async def test_unsafe_username_in_filename(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, username='we"ird name')
    disposition = (await _export(client)).headers["content-disposition"]
    assert 'filename="we_ird_name_2026-11-01' in disposition
