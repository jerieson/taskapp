"""Support dictionary: shared reading, author/admin editing, search and filters,
support types, and the admin CSV import.

tests/fixtures/support_sample.csv is synthetic but has the quirks of the team's sheet:
an author column headed "0", a "Data Modif" type, "- - - -" placeholders, a blank
project, a blank concern, an unknown type, a near-duplicate row and an empty row.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role, SupportEntry, SupportType, User
from tests.auth_helpers import login_as
from tests.factories import make_user

pytestmark = pytest.mark.anyio

SAMPLE = (Path(__file__).parent / "fixtures" / "support_sample.csv").read_bytes()
IMPORT_URL = "/api/admin/support/import"


async def _type(db: AsyncSession, label: str = "Concern") -> SupportType:
    row = await db.scalar(select(SupportType).where(SupportType.label == label))
    assert row is not None, label
    return row


async def _entry(db: AsyncSession, author: User, **kw: Any) -> SupportEntry:
    type_id = kw.pop("type_id", None) or (await _type(db)).id
    entry = SupportEntry(
        type_id=type_id,
        concern=kw.pop("concern", "Something broke"),
        created_by=author.id,
        updated_by=author.id,
        **kw,
    )
    db.add(entry)
    await db.flush()
    return entry


# ---------------------------------------------------------------- CRUD and permissions


async def test_create_and_read(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    type_ = await _type(db, "Bug")
    resp = await client.post(
        "/api/support",
        json={
            "type_id": type_.id,
            "project": " SFA Mobile ",
            "module": "",
            "concern": "  App crashes on sync ",
            "query": "\n    SELECT *\n    FROM t;  \n",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["type"]["label"] == "Bug"
    assert body["project"] == "SFA Mobile"
    assert body["module"] is None
    assert body["concern"] == "App crashes on sync"
    assert body["query"] == "    SELECT *\n    FROM t;"
    assert body["created_by"] == {"id": me.id, "username": me.username}
    assert body["can_edit"] is True

    resp = await client.get(f"/api/support/{body['id']}")
    assert resp.status_code == 200
    assert resp.json()["concern"] == "App crashes on sync"


async def test_create_validation(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    type_ = await _type(db)
    resp = await client.post("/api/support", json={"type_id": type_.id, "concern": "  "})
    assert resp.status_code == 422
    assert "concern" in resp.json()["error"]["fields"]

    type_.is_active = False
    await db.flush()
    resp = await client.post("/api/support", json={"type_id": type_.id, "concern": "X"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_reference"
    resp = await client.post("/api/support", json={"type_id": 999999, "concern": "X"})
    assert resp.status_code == 422


async def test_everyone_reads_all_entries(client: AsyncClient, db: AsyncSession) -> None:
    other = await make_user(db, role=Role.MANAGER)
    entry = await _entry(db, other, concern="Their entry")
    await login_as(client, db)  # a dev on another team

    resp = await client.get(f"/api/support/{entry.id}")
    assert resp.status_code == 200
    assert resp.json()["can_edit"] is False
    resp = await client.get("/api/support")
    assert [e["id"] for e in resp.json()["items"]] == [entry.id]


async def test_author_edits_own_entry(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    entry = await _entry(db, me, cause="Old cause")
    inquiry = await _type(db, "Inquiry")

    resp = await client.patch(
        f"/api/support/{entry.id}",
        json={"type_id": inquiry.id, "cause": None, "resolution": "Restart"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["type"]["id"] == inquiry.id
    assert body["cause"] is None
    assert body["resolution"] == "Restart"
    assert body["concern"] == "Something broke"

    resp = await client.patch(f"/api/support/{entry.id}", json={"concern": None})
    assert resp.status_code == 422


async def test_editing_someone_elses_entry_is_403(client: AsyncClient, db: AsyncSession) -> None:
    other = await make_user(db)
    entry = await _entry(db, other)
    await login_as(client, db, role=Role.MANAGER)

    resp = await client.patch(f"/api/support/{entry.id}", json={"concern": "Mine now"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "not_author"
    resp = await client.post(f"/api/support/{entry.id}/deactivate")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "not_author"
    resp = await client.patch("/api/support/999999", json={"concern": "X"})
    assert resp.status_code == 404


async def test_admin_edits_any_entry(client: AsyncClient, db: AsyncSession) -> None:
    other = await make_user(db)
    entry = await _entry(db, other)
    admin = await login_as(client, db, role=Role.ADMIN)

    resp = await client.patch(f"/api/support/{entry.id}", json={"notes": "Checked"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["notes"] == "Checked"
    assert body["created_by"]["id"] == other.id
    assert body["updated_by"]["id"] == admin.id
    assert body["can_edit"] is True
    resp = await client.post(f"/api/support/{entry.id}/deactivate")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


async def test_editing_keeps_an_inactive_type(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    old = await _type(db, "Transport")
    entry = await _entry(db, me, type_id=old.id)
    old.is_active = False
    await db.flush()

    resp = await client.patch(f"/api/support/{entry.id}", json={"type_id": old.id, "notes": "x"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["type"]["id"] == old.id
    assert resp.json()["type"]["is_active"] is False


async def test_deactivated_entries_are_hidden_by_default(
    client: AsyncClient, db: AsyncSession
) -> None:
    me = await login_as(client, db)
    live = await _entry(db, me, concern="Live")
    gone = await _entry(db, me, concern="Gone")

    resp = await client.post(f"/api/support/{gone.id}/deactivate")
    assert resp.status_code == 200
    resp = await client.get("/api/support")
    assert [e["id"] for e in resp.json()["items"]] == [live.id]
    resp = await client.get("/api/support", params={"include_inactive": "true"})
    assert {e["id"] for e in resp.json()["items"]} == {live.id, gone.id}
    # Still readable directly, and the author can bring it back.
    assert (await client.get(f"/api/support/{gone.id}")).status_code == 200
    resp = await client.post(f"/api/support/{gone.id}/activate")
    assert resp.json()["is_active"] is True


async def test_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/api/support")).status_code == 401
    assert (await client.get("/api/support/facets")).status_code == 401


# ---------------------------------------------------------------- search and filters


async def test_search_and_filters(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    bug = await _type(db, "Bug")
    a = await _entry(
        db,
        me,
        concern="No customer on device",
        project="SFA Mobile",
        module="Visit Management",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    b = await _entry(
        db,
        me,
        type_id=bug.id,
        concern="Discount missing",
        cause="ETL job still running",
        project="SFA Web",
        module="Booking",
        sub_module="Discounts",
        created_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    c = await _entry(
        db,
        me,
        concern="Report 100%_done wrong",
        notes="See the customer table",
        project="sfa mobile",
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
    )

    async def ids(**params: str | int) -> list[int]:
        resp = await client.get("/api/support", params=params)
        assert resp.status_code == 200, resp.text
        return [e["id"] for e in resp.json()["items"]]

    assert await ids() == [c.id, b.id, a.id]  # newest first
    assert await ids(q="CUSTOMER") == [c.id, a.id]  # concern and notes
    assert await ids(q="etl") == [b.id]  # cause
    assert await ids(q="discounts") == [b.id]  # sub-module
    assert await ids(q="visit") == [a.id]  # module
    assert await ids(q="web") == [b.id]  # project
    assert await ids(q="customer device") == [a.id]  # every word must match
    assert await ids(q="100%_") == [c.id]  # LIKE wildcards are literal
    assert await ids(q="%") == [c.id]
    assert await ids(type_id=bug.id) == [b.id]
    assert await ids(project="SFA MOBILE") == [c.id, a.id]
    assert await ids(module="booking") == [b.id]
    assert await ids(project="SFA Mobile", q="device") == [a.id]

    resp = await client.get("/api/support", params={"limit": 1, "offset": 1})
    body = resp.json()
    assert (body["total"], [e["id"] for e in body["items"]]) == (3, [b.id])


async def test_facets(client: AsyncClient, db: AsyncSession) -> None:
    me = await login_as(client, db)
    await _entry(db, me, project="SFA Web", module="Booking")
    await _entry(db, me, project="SFA Mobile", module="Visit Management", sub_module="Bookings")
    await _entry(db, me, project="sfa mobile")
    await _entry(db, me, project="Hidden", is_active=False)

    resp = await client.get("/api/support/facets")
    assert resp.status_code == 200
    assert resp.json() == {
        "projects": ["SFA Mobile", "SFA Web"],
        "modules": ["Booking", "Visit Management"],
        "sub_modules": ["Bookings"],
    }


# ---------------------------------------------------------------- support types


async def test_support_types_lookup(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db)
    resp = await client.get("/api/support-types")
    assert resp.status_code == 200
    assert [t["label"] for t in resp.json()["items"]] == [
        "Concern",
        "Inquiry",
        "Bug",
        "Request",
        "Data Modification",
        "Transport",
    ]
    resp = await client.post("/api/support-types", json={"label": "Escalation"})
    assert resp.status_code == 403


async def test_admin_manages_support_types(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    resp = await client.post("/api/support-types", json={"label": "Escalation", "color": "#aabbcc"})
    assert resp.status_code == 201, resp.text
    type_id = resp.json()["id"]
    assert resp.json()["color"] == "#AABBCC"
    resp = await client.post("/api/support-types", json={"label": "escalation"})
    assert resp.status_code == 409
    resp = await client.post(f"/api/support-types/{type_id}/deactivate")
    assert resp.json()["is_active"] is False
    resp = await client.get("/api/support-types")
    assert type_id not in [t["id"] for t in resp.json()["items"]]


# ---------------------------------------------------------------- CSV import


async def _import(client: AsyncClient, content: bytes = SAMPLE, **params: str) -> Any:
    return await client.post(
        IMPORT_URL, params=params, files={"file": ("Support.csv", content, "text/csv")}
    )


async def _entries(db: AsyncSession) -> list[SupportEntry]:
    rows = await db.scalars(
        select(SupportEntry).order_by(SupportEntry.id),
        execution_options={"populate_existing": True},
    )
    return list(rows)


async def test_import_sample(client: AsyncClient, db: AsyncSession) -> None:
    admin = await login_as(client, db, role=Role.ADMIN)
    eson = await make_user(db, username="eson")

    resp = await _import(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is False
    assert body["created"] == 4
    assert body["skipped"] == 2
    assert body["types_created"] == ["Escalation"]
    assert body["types_matched"] == [
        {"file_label": "Data Modif", "type_label": "Data Modification"}
    ]
    assert body["authors_matched"] == ["eson"]
    assert body["authors_unmatched"] == ["JP"]
    assert body["errors"] == [
        {"row": 5, "message": "Concern is blank"},
        {"row": 7, "message": "Same as row 2"},
    ]

    first, second, third, fourth = await _entries(db)
    # Author matched: that user is the author; dash placeholder blanked; SQL kept.
    assert first.created_by == eson.id
    assert first.updated_by == admin.id
    assert first.sub_module is None
    assert first.query is not None
    assert first.query.startswith("SELECT \n    *\nFROM")
    # Prefix type match, trimmed values, unknown author kept in the notes, dated row.
    assert (await db.get_one(SupportType, second.type_id)).label == "Data Modification"
    assert second.module == "CT Sales"
    assert second.created_by == admin.id
    assert second.notes == "Ask the lead first.\n\nAuthor: JP"
    assert second.created_at.date().isoformat() == "2025-07-10"
    # Blank project is allowed.
    assert third.project is None
    assert third.notes is None
    assert third.created_at.date().isoformat() == "2026-02-04"
    assert (await db.get_one(SupportType, fourth.type_id)).label == "Escalation"


async def test_import_twice_creates_nothing_new(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    assert (await _import(client)).json()["created"] == 4
    body = (await _import(client)).json()
    assert body["created"] == 0
    assert body["types_created"] == []
    assert len(await _entries(db)) == 4
    assert body["errors"][0] == {"row": 2, "message": "Already in the dictionary"}


async def test_import_dry_run_saves_nothing(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    resp = await _import(client, dry_run="true")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["dry_run"], body["created"], body["types_created"]) == (True, 4, ["Escalation"])
    assert await _entries(db) == []
    count = await db.scalar(
        select(func.count()).select_from(SupportType).where(SupportType.label == "Escalation")
    )
    assert count == 0


async def test_import_row_errors(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    long_project = "P" * 101
    content = (
        "Author,Type,Project,Concern\n"
        f"x,Bug,{long_project},Too long\n"
        ",,SFA,No type\n"
        f",{'T' * 51},SFA,Long type\n"
        ",Bug,SFA,Fine\n"
    ).encode()
    body = (await _import(client, content)).json()
    assert body["created"] == 1
    assert body["errors"] == [
        {"row": 2, "message": "Project is longer than 100 characters"},
        {"row": 3, "message": "Type is blank"},
        {"row": 4, "message": "Type is longer than 50 characters"},
    ]


async def test_import_rejects_bad_files(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.ADMIN)
    resp = await _import(client, b"Author,Project,Notes\nx,y,z\n")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_file"
    assert "Type and Concern" in resp.json()["error"]["message"]
    resp = await _import(client, b"\xff\xfe\x00")
    assert resp.status_code == 422


async def test_import_is_admin_only(client: AsyncClient, db: AsyncSession) -> None:
    await login_as(client, db, role=Role.MANAGER)
    assert (await _import(client)).status_code == 403
