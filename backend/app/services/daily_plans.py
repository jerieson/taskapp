"""Daily plans. Every user (admin included) sees and changes only their own plans.

Rules enforced here:
- A plan someone else owns is reported as 404, never 403 (also its items).
- Items can only be the plan owner's own open tasks (status not `is_done`), checked
  when they are added. A task completed later stays in the plan, shown as done.
- A task appears at most once per plan (409 `duplicate_task`).
- Writes lock the plan row, so concurrent edits of one plan run one after another.
- `item_order` is kept as 0..n-1 after every write.
"""

import logging
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import DailyPlan, DailyPlanItem, Status, Task, User
from app.schemas.daily_plans import (
    DailyPlanOut,
    PlanItemCreate,
    PlanItemOut,
    PlanItemsReplace,
    PlanItemUpdate,
    PlanOrder,
)
from app.services.refs import invalid_reference
from app.services.tasks import task_out, task_query

logger = logging.getLogger("app.daily_plans")


def _not_found() -> AppError:
    return AppError(404, "not_found", "Plan not found")


async def _load(
    db: AsyncSession, plan: DailyPlan, today: date, workday_hours: Decimal
) -> DailyPlanOut:
    plan_items = await _items(db, plan)
    rows = await db.execute(
        task_query()
        .where(Task.id.in_([item.task_id for item in plan_items]))
        .execution_options(populate_existing=True)
    )
    tasks = {row[0].id: task_out(row, today) for row in rows.all()}
    items = [
        PlanItemOut(
            id=item.id,
            item_order=item.item_order,
            suggested_hours=item.suggested_hours,
            ai_reason=item.ai_reason,
            task=tasks[item.task_id],
        )
        for item in plan_items
    ]
    return DailyPlanOut(
        id=plan.id,
        plan_date=plan.plan_date,
        ai_generated=plan.ai_generated,
        created_at=plan.created_at,
        items=items,
        total_hours=sum((i.suggested_hours or Decimal(0) for i in items), Decimal(0)),
        workday_hours=workday_hours,
    )


async def _get_own(db: AsyncSession, user: User, plan_id: int, *, lock: bool) -> DailyPlan:
    stmt = select(DailyPlan).where(DailyPlan.id == plan_id, DailyPlan.user_id == user.id)
    if lock:
        stmt = stmt.with_for_update()
    plan = await db.scalar(stmt)
    if plan is None:
        raise _not_found()
    return plan


async def _get_item(db: AsyncSession, plan: DailyPlan, item_id: int) -> DailyPlanItem:
    item = await db.scalar(
        select(DailyPlanItem).where(
            DailyPlanItem.id == item_id, DailyPlanItem.daily_plan_id == plan.id
        )
    )
    if item is None:
        raise AppError(404, "not_found", "Plan item not found")
    return item


async def _items(db: AsyncSession, plan: DailyPlan) -> Sequence[DailyPlanItem]:
    return (
        await db.scalars(
            select(DailyPlanItem)
            .where(DailyPlanItem.daily_plan_id == plan.id)
            .order_by(DailyPlanItem.item_order, DailyPlanItem.id)
        )
    ).all()


async def _open_task_ids(db: AsyncSession, user: User, task_ids: list[int]) -> set[int]:
    """Which of `task_ids` are the user's own tasks with a status that is not done."""
    if not task_ids:
        return set()
    rows = await db.scalars(
        select(Task.id)
        .join(Status, Status.id == Task.status_id)
        .where(Task.id.in_(task_ids), Task.user_id == user.id, ~Status.is_done)
    )
    return set(rows.all())


_OPEN_TASK_MESSAGE = "Choose one of your open tasks"


def _renumber(items: Sequence[DailyPlanItem]) -> None:
    for order, item in enumerate(items):
        item.item_order = order


# ---------------------------------------------------------------- reads


async def open_plan(
    db: AsyncSession, user: User, plan_date: date, today: date, workday_hours: Decimal
) -> DailyPlanOut:
    """The caller's plan for `plan_date`, created (empty) if there is none yet."""
    await db.execute(
        insert(DailyPlan)
        .values(user_id=user.id, plan_date=plan_date)
        .on_conflict_do_nothing(index_elements=["user_id", "plan_date"])
    )
    await db.commit()
    plan = (
        await db.scalars(
            select(DailyPlan).where(DailyPlan.user_id == user.id, DailyPlan.plan_date == plan_date)
        )
    ).one()
    return await _load(db, plan, today, workday_hours)


async def get_plan_by_date(
    db: AsyncSession, user: User, plan_date: date, today: date, workday_hours: Decimal
) -> DailyPlanOut:
    """The caller's plan for `plan_date`, or 404 if none has been created."""
    plan = await db.scalar(
        select(DailyPlan).where(DailyPlan.user_id == user.id, DailyPlan.plan_date == plan_date)
    )
    if plan is None:
        raise _not_found()
    return await _load(db, plan, today, workday_hours)


async def get_plan(
    db: AsyncSession, user: User, plan_id: int, today: date, workday_hours: Decimal
) -> DailyPlanOut:
    plan = await _get_own(db, user, plan_id, lock=False)
    return await _load(db, plan, today, workday_hours)


# ---------------------------------------------------------------- writes


async def add_item(
    db: AsyncSession,
    user: User,
    plan_id: int,
    data: PlanItemCreate,
    today: date,
    workday_hours: Decimal,
) -> DailyPlanOut:
    """Appends the task at the end of the plan."""
    plan = await _get_own(db, user, plan_id, lock=True)
    if not await _open_task_ids(db, user, [data.task_id]):
        raise invalid_reference("task_id", _OPEN_TASK_MESSAGE)
    existing = await _items(db, plan)
    if any(item.task_id == data.task_id for item in existing):
        message = "This task is already in the plan"
        raise AppError(409, "duplicate_task", message, fields={"task_id": message})

    db.add(
        DailyPlanItem(
            daily_plan_id=plan.id,
            task_id=data.task_id,
            item_order=len(existing),
            suggested_hours=data.suggested_hours,
        )
    )
    _renumber(existing)
    await db.commit()
    logger.info("plan_item_added", extra={"fields": {"plan_id": plan.id}})
    return await _load(db, plan, today, workday_hours)


async def update_item(
    db: AsyncSession,
    user: User,
    plan_id: int,
    item_id: int,
    data: PlanItemUpdate,
    today: date,
    workday_hours: Decimal,
) -> DailyPlanOut:
    plan = await _get_own(db, user, plan_id, lock=True)
    item = await _get_item(db, plan, item_id)
    item.suggested_hours = data.suggested_hours
    await db.commit()
    return await _load(db, plan, today, workday_hours)


async def remove_item(db: AsyncSession, user: User, plan_id: int, item_id: int) -> None:
    plan = await _get_own(db, user, plan_id, lock=True)
    item = await _get_item(db, plan, item_id)
    await db.delete(item)
    await db.flush()
    _renumber(await _items(db, plan))
    await db.commit()
    logger.info("plan_item_removed", extra={"fields": {"plan_id": plan.id}})


async def reorder(
    db: AsyncSession,
    user: User,
    plan_id: int,
    data: PlanOrder,
    today: date,
    workday_hours: Decimal,
) -> DailyPlanOut:
    plan = await _get_own(db, user, plan_id, lock=True)
    by_id = {item.id: item for item in await _items(db, plan)}
    if set(data.item_ids) != set(by_id):
        message = "List every item of the plan exactly once"
        raise AppError(422, "invalid_order", message, fields={"item_ids": message})
    _renumber([by_id[item_id] for item_id in data.item_ids])
    await db.commit()
    return await _load(db, plan, today, workday_hours)


async def replace_items(
    db: AsyncSession,
    user: User,
    plan_id: int,
    data: PlanItemsReplace,
    today: date,
    workday_hours: Decimal,
) -> DailyPlanOut:
    """Swaps all of the plan's items in one transaction (all or nothing).

    Every task must be one of the caller's open tasks. The new list fully replaces
    the old one, including hours and AI reasons.
    """
    plan = await _get_own(db, user, plan_id, lock=True)
    task_ids = [item.task_id for item in data.items]
    open_ids = await _open_task_ids(db, user, task_ids)
    for index, task_id in enumerate(task_ids):
        if task_id not in open_ids:
            raise invalid_reference(f"items.{index}.task_id", _OPEN_TASK_MESSAGE)

    await db.execute(delete(DailyPlanItem).where(DailyPlanItem.daily_plan_id == plan.id))
    db.add_all(
        DailyPlanItem(
            daily_plan_id=plan.id,
            task_id=item.task_id,
            item_order=order,
            suggested_hours=item.suggested_hours,
        )
        for order, item in enumerate(data.items)
    )
    await db.commit()
    logger.info(
        "plan_items_replaced", extra={"fields": {"plan_id": plan.id, "items": len(data.items)}}
    )
    return await _load(db, plan, today, workday_hours)
