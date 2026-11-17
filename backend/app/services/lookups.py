"""Dropdown values: categories, statuses and priorities.

Rows are never deleted, only deactivated. Code never refers to a row by its label;
it uses the is_default / is_done flags. Rules enforced here:

- Statuses and priorities have exactly one default, which must be active. Setting a
  new default moves the flag; the default cannot be deactivated.
- At least one active status with is_done must remain (once one exists).

Every write takes a per-table transaction advisory lock first, so concurrent admin
edits are serialised and the checks above cannot race each other.
"""

import logging

from sqlalchemy import exists, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.pagination import Page, PaginationParams
from app.models import Category, Priority, Role, Status, User
from app.schemas.lookups import CategoryOut, LookupCreate, LookupUpdate, StatusCreate, StatusUpdate

logger = logging.getLogger("app.lookups")

type LookupModel = type[Category] | type[Status] | type[Priority]
type LookupRow = Category | Status | Priority

_NOUN: dict[type, str] = {Category: "category", Status: "status", Priority: "priority"}


def _has_default(model: LookupModel) -> bool:
    return model is not Category


async def lock_table(db: AsyncSession, table: str) -> None:
    """Serialise writers of `table` until the transaction ends."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"lookups:{table}"}
    )


def ensure_can_include_inactive(user: User, include_inactive: bool) -> None:
    if include_inactive and user.role != Role.ADMIN:
        raise AppError(403, "forbidden", "Only admins can list inactive values")


def _label_taken(model: LookupModel) -> AppError:
    message = f"A {_NOUN[model]} with this label already exists"
    return AppError(409, "label_taken", message, fields={"label": message})


async def _get(db: AsyncSession, model: LookupModel, row_id: int) -> LookupRow:
    row = await db.get(model, row_id, populate_existing=True)
    if row is None:
        raise AppError(404, "not_found", f"{_NOUN[model].capitalize()} not found")
    return row


async def _ensure_label_free(
    db: AsyncSession, model: LookupModel, label: str, exclude_id: int | None = None
) -> None:
    cond = func.lower(model.label) == label.lower()
    if exclude_id is not None:
        cond = cond & (model.id != exclude_id)
    if await db.scalar(select(exists().where(cond))):
        raise _label_taken(model)


async def _commit(db: AsyncSession, model: LookupModel) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:  # only the unique label can fail after our checks
        await db.rollback()
        raise _label_taken(model) from exc


async def _ensure_other_done_status(db: AsyncSession, status: Status) -> None:
    """Reject removing the last active done status."""
    others = await db.scalar(
        select(exists().where(Status.is_active, Status.is_done, Status.id != status.id))
    )
    if not others:
        message = "At least one active status must count as done"
        raise AppError(409, "last_done_status", message, fields={"is_done": message})


async def list_values[O: CategoryOut](
    db: AsyncSession,
    model: LookupModel,
    out: type[O],
    params: PaginationParams,
    include_inactive: bool,
) -> Page[O]:
    stmt = select(model)
    if not include_inactive:
        stmt = stmt.where(model.is_active)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.scalars(
        stmt.order_by(model.sort_order, model.id).limit(params.limit).offset(params.offset)
    )
    return Page[out].build(rows.all(), total, params)


async def create_value(db: AsyncSession, model: LookupModel, data: LookupCreate) -> LookupRow:
    await lock_table(db, model.__tablename__)
    await _ensure_label_free(db, model, data.label)
    last = await db.scalar(select(func.max(model.sort_order)))
    row = model(label=data.label, color=data.color, sort_order=(last or 0) + 1, is_active=True)
    if isinstance(data, StatusCreate):
        row.is_done = data.is_done
    if _has_default(model):
        # The first value (or the first after data loss) becomes the default.
        row.is_default = not await db.scalar(select(exists().where(model.is_default)))
    db.add(row)
    await _commit(db, model)
    await db.refresh(row)
    logger.info("lookup_created", extra={"fields": {"table": model.__tablename__, "id": row.id}})
    return row


async def update_value(
    db: AsyncSession, model: LookupModel, row_id: int, data: LookupUpdate
) -> LookupRow:
    await lock_table(db, model.__tablename__)
    row = await _get(db, model, row_id)
    sent = data.model_fields_set
    if data.label is not None and data.label != row.label:
        await _ensure_label_free(db, model, data.label, exclude_id=row.id)
        row.label = data.label
    if "color" in sent:
        row.color = data.color
    if isinstance(row, Status) and isinstance(data, StatusUpdate) and data.is_done is not None:
        if row.is_done and not data.is_done and row.is_active:
            await _ensure_other_done_status(db, row)
        row.is_done = data.is_done
    await _commit(db, model)
    await db.refresh(row)
    logger.info("lookup_updated", extra={"fields": {"table": model.__tablename__, "id": row.id}})
    return row


async def set_active(db: AsyncSession, model: LookupModel, row_id: int, active: bool) -> LookupRow:
    await lock_table(db, model.__tablename__)
    row = await _get(db, model, row_id)
    if not active and row.is_active:
        if isinstance(row, Status | Priority) and row.is_default:
            raise AppError(
                409,
                "default_cannot_be_deactivated",
                f"Make another {_NOUN[model]} the default before deactivating this one",
            )
        if isinstance(row, Status) and row.is_done:
            await _ensure_other_done_status(db, row)
    row.is_active = active
    await db.commit()
    await db.refresh(row)
    logger.info(
        "lookup_activated" if active else "lookup_deactivated",
        extra={"fields": {"table": model.__tablename__, "id": row.id}},
    )
    return row


async def set_default(
    db: AsyncSession, model: type[Status] | type[Priority], row_id: int
) -> Status | Priority:
    """Move the default flag to `row_id` in one transaction."""
    await lock_table(db, model.__tablename__)
    row = await db.get(model, row_id, populate_existing=True)
    if row is None:
        raise AppError(404, "not_found", f"{_NOUN[model].capitalize()} not found")
    if not row.is_active:
        raise AppError(
            409, "inactive_cannot_be_default", "Activate this value before making it the default"
        )
    if not row.is_default:
        current = await db.scalars(select(model).where(model.is_default, model.id != row.id))
        for old in current:
            old.is_default = False
        # Two flushes: the single-default partial unique index is not deferrable.
        await db.flush()
        row.is_default = True
        await db.commit()
        await db.refresh(row)
        logger.info(
            "lookup_default_set", extra={"fields": {"table": model.__tablename__, "id": row.id}}
        )
    return row


async def reorder(db: AsyncSession, model: LookupModel, ids: list[int]) -> None:
    """Set sort_order from `ids`, which must list every row exactly once."""
    await lock_table(db, model.__tablename__)
    rows = {row.id: row for row in await db.scalars(select(model))}
    if len(ids) != len(set(ids)) or set(ids) != set(rows):
        message = "Send every id exactly once, in the new order"
        raise AppError(422, "validation_error", message, fields={"ids": message})
    for position, row_id in enumerate(ids, start=1):
        rows[row_id].sort_order = position
    await db.commit()
    logger.info("lookup_reordered", extra={"fields": {"table": model.__tablename__}})
