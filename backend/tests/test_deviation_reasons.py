"""Reason for Deviation: an admin-managed dropdown, optional on log rows."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Role
from tests.auth_helpers import login_as
from tests.factories import make_deviation_reason, make_linked, make_log

pytestmark = pytest.mark.anyio


async def test_seeded_in_sheet_order(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    items = (await client.get("/api/deviation-reasons")).json()["items"]
    labels = [item["label"] for item in items]
    assert labels[:3] == ["Unplanned Leaves", "Support Issue Prioritization", "Unplanned Meetings"]
    assert labels[-1] == "Document Revision"
    assert len(labels) == 11
    options = (await client.get("/api/log-options")).json()
    assert [r["label"] for r in options["deviation_reasons"]] == labels
    assert options["workday_hours"] == float(get_settings().workday_hours)


async def test_admin_manages_values(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    resp = await client.post("/api/deviation-reasons", json={"label": "Hardware Failure"})
    assert resp.status_code == 201, resp.text
    reason_id = resp.json()["id"]
    resp = await client.post(f"/api/deviation-reasons/{reason_id}/deactivate")
    assert resp.json()["is_active"] is False
    labels = [
        r["label"] for r in (await client.get("/api/log-options")).json()["deviation_reasons"]
    ]
    assert "Hardware Failure" not in labels
    dup = await client.post("/api/deviation-reasons", json={"label": "scope creep"})
    assert dup.status_code == 409


async def test_dev_cannot_write(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    resp = await client.post("/api/deviation-reasons", json={"label": "Mine"})
    assert resp.status_code == 403


async def test_on_log_rows(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    refs = await make_linked(db)
    active = await make_deviation_reason(db)
    inactive = await make_deviation_reason(db, is_active=False)
    body = {"log_date": "2026-11-02", "hours_spent": 2, **refs.ids()}

    resp = await client.post("/api/logs", json={**body, "deviation_reason_id": inactive.id})
    assert resp.status_code == 422
    assert "deviation_reason_id" in resp.json()["error"]["fields"]
    resp = await client.post("/api/logs", json=body)
    assert resp.json()["deviation_reason"] is None  # optional, blank by default

    # An inactive value already on a row stays; it can be cleared.
    log = await make_log(db, user=me, deviation_reason_id=inactive.id, **refs.ids())
    url = f"/api/logs/{log.id}"
    resp = await client.patch(url, json={"deviation_reason_id": inactive.id, "hours_spent": 3})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deviation_reason"]["is_active"] is False
    resp = await client.patch(url, json={"deviation_reason_id": active.id})
    assert resp.json()["deviation_reason"]["id"] == active.id
    resp = await client.patch(url, json={"deviation_reason_id": None})
    assert resp.json()["deviation_reason"] is None
