"""Dropdown values: categories, statuses, priorities, work set-ups, activities,
activity groups and O&M projects.

Rows are never deleted, only deactivated. Code never refers to a row by its label;
it uses the is_default / is_done / requires_om_project flags. Rules enforced here:

- Statuses, priorities and work set-ups have exactly one default, which must be active.
  Setting a new default moves the flag; the default cannot be deactivated.
- At least one active status with is_done must remain (once one exists).
- An activity group's members are replaced as a whole; newly added activities must be
  active, inactive members already in the group may stay.

Every write takes a per-table transaction advisory lock first, so concurrent admin
edits are serialised and the checks above cannot race each other.
"""

import logging
from typing import Any

from pydantic import BaseModel
from sqlalchemy import exists, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.pagination import Page, PaginationParams
from app.models import (
    Activity,
    ActivityGroup,
    ActivityGroupMember,
    Category,
    DeviationReason,
    OmProject,
    Priority,
    Role,
    Status,
    User,
    WorkSetup,
)

logger = logging.getLogger("app.lookups")

type LookupRow = (
    Category
    | Status
    | Priority
    | WorkSetup
    | Activity
    | ActivityGroup
    | OmProject
    | DeviationReason
)
type LookupModel = (
    type[Category]
    | type[Status]
    | type[Priority]
    | type[WorkSetup]
    | type[Activity]
    | type[ActivityGroup]
    | type[OmProject]
    | type[DeviationReason]
)
type DefaultModel = type[Status] | type[Priority] | type[WorkSetup]

NOUN: dict[type, str] = {
    Category: "category",
    Status: "status",
    Priority: "priority",
    WorkSetup: "work set-up",
    Activity: "activity",
    ActivityGroup: "activity group",
    OmProject: "O&M project",
    DeviationReason: "reason for deviation",
}


def _has(model: LookupModel, column: str) -> bool:
    return column in model.__table__.columns


async def lock_table(db: AsyncSession, table: str) -> None:
    """Serialise writers of `table` until the transaction ends."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"lookups:{table}"}
    )


def ensure_can_include_inactive(user: User, include_inactive: bool) -> None:
    if include_inactive and user.role != Role.ADMIN:
        raise AppError(403, "forbidden", "Only admins can list inactive values")


def _label_taken(model: LookupModel) -> AppError:
    message = f"A {NOUN[model]} with this label already exists"
    return AppError(409, "label_taken", message, fields={"label": message})


async def _get[R: LookupRow](db: AsyncSession, model: type[R], row_id: int) -> R:
    row = await db.get(model, row_id, populate_existing=True)
    if row is None:
        raise AppError(404, "not_found", f"{NOUN[model].capitalize()} not found")
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


async def list_values[O: BaseModel](
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


async def create_value(db: AsyncSession, model: LookupModel, data: BaseModel) -> LookupRow:
    """`data` has `label` and optionally `color`, `is_done`, `requires_om_project`
    (each only for the tables that have that column)."""
    await lock_table(db, model.__tablename__)
    values: dict[str, Any] = data.model_dump()
    await _ensure_label_free(db, model, values["label"])
    last = await db.scalar(select(func.max(model.sort_order)))
    row = model(**values, sort_order=(last or 0) + 1, is_active=True)
    if _has(model, "is_default"):
        # The first value (or the first after data loss) becomes the default.
        row.is_default = not await db.scalar(select(exists().where(model.is_default)))
    db.add(row)
    await _commit(db, model)
    await db.refresh(row)
    logger.info("lookup_created", extra={"fields": {"table": model.__tablename__, "id": row.id}})
    return row


async def update_value(
    db: AsyncSession, model: LookupModel, row_id: int, data: BaseModel
) -> LookupRow:
    """Omitted fields keep their value; `color` may be cleared with null."""
    await lock_table(db, model.__tablename__)
    row = await _get(db, model, row_id)
    values: dict[str, Any] = data.model_dump(exclude_unset=True)
    label = values.pop("label", None)
    if label is not None and label != row.label:
        await _ensure_label_free(db, model, label, exclude_id=row.id)
        row.label = label
    if "color" in values:
        row.color = values.pop("color")
    is_done = values.pop("is_done", None)
    if isinstance(row, Status) and is_done is not None:
        if row.is_done and not is_done and row.is_active:
            await _ensure_other_done_status(db, row)
        row.is_done = is_done
    requires_om_project = values.pop("requires_om_project", None)
    if isinstance(row, Category) and requires_om_project is not None:
        row.requires_om_project = requires_om_project
    await _commit(db, model)
    await db.refresh(row)
    logger.info("lookup_updated", extra={"fields": {"table": model.__tablename__, "id": row.id}})
    return row


async def set_active(db: AsyncSession, model: LookupModel, row_id: int, active: bool) -> LookupRow:
    await lock_table(db, model.__tablename__)
    row = await _get(db, model, row_id)
    if not active and row.is_active:
        if isinstance(row, Status | Priority | WorkSetup) and row.is_default:
            raise AppError(
                409,
                "default_cannot_be_deactivated",
                f"Make another {NOUN[model]} the default before deactivating this one",
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
    db: AsyncSession, model: DefaultModel, row_id: int
) -> Status | Priority | WorkSetup:
    """Move the default flag to `row_id` in one transaction."""
    await lock_table(db, model.__tablename__)
    row = await db.get(model, row_id, populate_existing=True)
    if row is None:
        raise AppError(404, "not_found", f"{NOUN[model].capitalize()} not found")
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


async def set_group_activities(
    db: AsyncSession, group_id: int, activity_ids: list[int]
) -> ActivityGroup:
    """Replace the group's members with `activity_ids`, in that order."""
    await lock_table(db, ActivityGroup.__tablename__)
    group = await _get(db, ActivityGroup, group_id)
    if len(activity_ids) != len(set(activity_ids)):
        message = "List each activity once"
        raise AppError(422, "validation_error", message, fields={"activity_ids": message})
    current = {member.activity_id: member for member in group.members}
    found = {
        activity.id: activity
        for activity in await db.scalars(select(Activity).where(Activity.id.in_(activity_ids)))
    }
    for activity_id in activity_ids:
        activity = found.get(activity_id)
        if activity is None or (not activity.is_active and activity_id not in current):
            message = "Choose active activities"
            raise AppError(422, "invalid_reference", message, fields={"activity_ids": message})
    members = []
    for position, activity_id in enumerate(activity_ids, start=1):
        member = current.get(activity_id) or ActivityGroupMember(activity_id=activity_id)
        member.sort_order = position
        members.append(member)
    group.members = members
    await db.commit()
    await db.refresh(group)
    logger.info("activity_group_members_set", extra={"fields": {"id": group.id}})
    return group
