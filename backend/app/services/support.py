"""Support dictionary entries, shared by everyone.

Rules enforced here:
- Everyone lists and reads every entry (inactive ones only when asked for).
- Anyone creates; only the author or an admin edits or (de)activates. Others get
  403 `not_author`: the entry is readable, so a 404 would be misleading.
- Entries are never deleted.
- New entries need an active type; an edit may keep the type already on the entry.
"""

import logging
import re

from sqlalchemy import Row, Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, aliased

from app.core.errors import AppError
from app.core.pagination import Page
from app.models import Role, SupportEntry, SupportType, User
from app.schemas.prod_logs import UserRef
from app.schemas.support import (
    SupportEntryCreate,
    SupportEntryOut,
    SupportEntryUpdate,
    SupportFacets,
    SupportQuery,
)
from app.schemas.tasks import LookupRef
from app.services.refs import check_ref

logger = logging.getLogger("app.support")

_Author = aliased(User)
_Editor = aliased(User)

type _Row = tuple[SupportEntry, SupportType, User, User]

SEARCH_COLUMNS = (
    SupportEntry.concern,
    SupportEntry.cause,
    SupportEntry.resolution,
    SupportEntry.notes,
    SupportEntry.project,
    SupportEntry.module,
    SupportEntry.sub_module,
)


def _query() -> Select[_Row]:
    return (
        select(SupportEntry, SupportType, _Author, _Editor)
        .join(SupportType, SupportType.id == SupportEntry.type_id)
        .join(_Author, _Author.id == SupportEntry.created_by)
        .join(_Editor, _Editor.id == SupportEntry.updated_by)
    )


def can_edit(user: User, entry: SupportEntry) -> bool:
    return user.role == Role.ADMIN or entry.created_by == user.id


def _out(row: Row[_Row], user: User) -> SupportEntryOut:
    entry, type_, author, editor = row
    return SupportEntryOut(
        id=entry.id,
        type=LookupRef.model_validate(type_),
        project=entry.project,
        module=entry.module,
        sub_module=entry.sub_module,
        concern=entry.concern,
        cause=entry.cause,
        resolution=entry.resolution,
        query=entry.query,
        notes=entry.notes,
        is_active=entry.is_active,
        created_by=UserRef.model_validate(author),
        updated_by=UserRef.model_validate(editor),
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        can_edit=can_edit(user, entry),
    )


def _like(word: str) -> str:
    escaped = re.sub(r"([\\%_])", r"\\\1", word)
    return f"%{escaped}%"


async def list_entries(db: AsyncSession, user: User, params: SupportQuery) -> Page[SupportEntryOut]:
    stmt = _query()
    if not params.include_inactive:
        stmt = stmt.where(SupportEntry.is_active)
    if params.type_id is not None:
        stmt = stmt.where(SupportEntry.type_id == params.type_id)
    if params.project:
        stmt = stmt.where(func.lower(SupportEntry.project) == params.project.lower())
    if params.module:
        stmt = stmt.where(func.lower(SupportEntry.module) == params.module.lower())
    if params.q:
        stmt = stmt.where(
            and_(
                *(
                    or_(*(col.ilike(_like(word), escape="\\") for col in SEARCH_COLUMNS))
                    for word in params.q.split()
                )
            )
        )
    stmt = stmt.order_by(SupportEntry.created_at.desc(), SupportEntry.id.desc())
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = await db.execute(stmt.limit(params.limit).offset(params.offset))
    return Page[SupportEntryOut].build([_out(r, user) for r in rows.all()], total, params)


async def _load(db: AsyncSession, user: User, entry_id: int) -> SupportEntryOut:
    row = (await db.execute(_query().where(SupportEntry.id == entry_id))).one_or_none()
    if row is None:
        raise AppError(404, "not_found", "Support entry not found")
    return _out(row, user)


async def get_entry(db: AsyncSession, user: User, entry_id: int) -> SupportEntryOut:
    return await _load(db, user, entry_id)


async def _get_editable(db: AsyncSession, user: User, entry_id: int) -> SupportEntry:
    entry = await db.get(SupportEntry, entry_id, populate_existing=True)
    if entry is None:
        raise AppError(404, "not_found", "Support entry not found")
    if not can_edit(user, entry):
        raise AppError(403, "not_author", "Only the author or an admin can change this entry")
    return entry


async def create_entry(db: AsyncSession, user: User, data: SupportEntryCreate) -> SupportEntryOut:
    await check_ref(db, "type_id", data.type_id, keep=None)
    entry = SupportEntry(**data.model_dump(), created_by=user.id, updated_by=user.id)
    db.add(entry)
    await db.commit()
    logger.info("support_entry_created", extra={"fields": {"entry_id": entry.id}})
    return await _load(db, user, entry.id)


async def update_entry(
    db: AsyncSession, user: User, entry_id: int, data: SupportEntryUpdate
) -> SupportEntryOut:
    entry = await _get_editable(db, user, entry_id)
    values = data.model_dump(exclude_unset=True)
    for field in ("type_id", "concern"):
        if field in values and values[field] is None:
            message = "This field is required"
            raise AppError(422, "validation_error", message, fields={field: message})
    if "type_id" in values:
        await check_ref(db, "type_id", values["type_id"], keep=entry.type_id)
    for field, value in values.items():
        setattr(entry, field, value)
    entry.updated_by = user.id
    await db.commit()
    logger.info("support_entry_updated", extra={"fields": {"entry_id": entry.id}})
    return await _load(db, user, entry.id)


async def set_active(db: AsyncSession, user: User, entry_id: int, active: bool) -> SupportEntryOut:
    entry = await _get_editable(db, user, entry_id)
    if entry.is_active != active:
        entry.is_active = active
        entry.updated_by = user.id
        await db.commit()
        logger.info(
            "support_entry_activated" if active else "support_entry_deactivated",
            extra={"fields": {"entry_id": entry.id}},
        )
    return await _load(db, user, entry.id)


async def facets(db: AsyncSession) -> SupportFacets:
    async def distinct_values(column: InstrumentedAttribute[str | None]) -> list[str]:
        rows = await db.scalars(
            select(column).distinct().where(SupportEntry.is_active, column.is_not(None))
        )
        # Case-insensitive de-duplication; the first spelling (alphabetically) wins.
        seen: dict[str, str] = {}
        for value in sorted((v for v in rows.all() if v), key=lambda v: (v.lower(), v)):
            seen.setdefault(value.lower(), value)
        return list(seen.values())

    return SupportFacets(
        projects=await distinct_values(SupportEntry.project),
        modules=await distinct_values(SupportEntry.module),
        sub_modules=await distinct_values(SupportEntry.sub_module),
    )
