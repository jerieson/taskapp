"""Personal processes and their steps. Every user (admin included) sees and changes
only the processes they own.

Rules enforced here:
- A process someone else owns is reported as 404, never 403 (also its steps).
- A process can be deleted only while it has no runs (409 `process_has_runs`);
  otherwise it is deactivated.
- A step's default category must be active when chosen; a category that was
  deactivated later may stay on the step.
- Changing or deleting steps never touches tasks already copied into runs (deleting
  a step only clears those tasks' `process_step_id`, via the foreign key).
- Writes lock the process row, so concurrent edits (and run starts) of one process
  run one after another. `step_order` is kept as 0..n-1 after every write.
"""

import logging
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.pagination import Page, paginate
from app.db.base import utcnow
from app.models import Category, Process, ProcessRun, ProcessStep, RunStatus, User
from app.schemas.processes import (
    MAX_STEPS,
    ProcessCreate,
    ProcessListItem,
    ProcessOut,
    ProcessQuery,
    ProcessStepOut,
    ProcessUpdate,
    StepCreate,
    StepOrder,
    StepsSync,
    StepUpdate,
)
from app.schemas.tasks import LookupRef
from app.services.refs import check_ref

logger = logging.getLogger("app.processes")


def _not_found() -> AppError:
    return AppError(404, "not_found", "Process not found")


async def get_own(db: AsyncSession, user: User, process_id: int, *, lock: bool) -> Process:
    """The caller's process, or 404 (also when it belongs to someone else)."""
    stmt = select(Process).where(Process.id == process_id, Process.owner_id == user.id)
    if lock:
        stmt = stmt.with_for_update()
    process = await db.scalar(stmt)
    if process is None:
        raise _not_found()
    return process


async def steps_in_order(db: AsyncSession, process_id: int) -> Sequence[ProcessStep]:
    return (
        await db.scalars(
            select(ProcessStep)
            .where(ProcessStep.process_id == process_id)
            .order_by(ProcessStep.step_order, ProcessStep.id)
        )
    ).all()


async def _get_step(db: AsyncSession, process: Process, step_id: int) -> ProcessStep:
    step = await db.scalar(
        select(ProcessStep).where(ProcessStep.id == step_id, ProcessStep.process_id == process.id)
    )
    if step is None:
        raise AppError(404, "not_found", "Step not found")
    return step


def _renumber(steps: Sequence[ProcessStep]) -> None:
    for order, step in enumerate(steps):
        step.step_order = order


async def _counts(db: AsyncSession, process_ids: list[int]) -> dict[int, tuple[int, int, int]]:
    """process id -> (step count, run count, in-progress run count)."""
    if not process_ids:
        return {}
    step_rows = await db.execute(
        select(ProcessStep.process_id, func.count())
        .where(ProcessStep.process_id.in_(process_ids))
        .group_by(ProcessStep.process_id)
    )
    steps: dict[int, int] = dict(step_rows.all())
    run_rows = await db.execute(
        select(
            ProcessRun.process_id,
            func.count(),
            func.count().filter(ProcessRun.status == RunStatus.IN_PROGRESS),
        )
        .where(ProcessRun.process_id.in_(process_ids))
        .group_by(ProcessRun.process_id)
    )
    runs: dict[int, tuple[int, int]] = {
        process_id: (total, active) for process_id, total, active in run_rows.all()
    }
    return {pid: (steps.get(pid, 0), *runs.get(pid, (0, 0))) for pid in process_ids}


def _list_item(process: Process, counts: tuple[int, int, int]) -> ProcessListItem:
    step_count, run_count, active_run_count = counts
    return ProcessListItem(
        id=process.id,
        name=process.name,
        description=process.description,
        is_active=process.is_active,
        step_count=step_count,
        run_count=run_count,
        active_run_count=active_run_count,
        created_at=process.created_at,
        updated_at=process.updated_at,
    )


async def _load(db: AsyncSession, process: Process) -> ProcessOut:
    await db.refresh(process)
    rows = await db.execute(
        select(ProcessStep, Category)
        .outerjoin(Category, Category.id == ProcessStep.default_category_id)
        .where(ProcessStep.process_id == process.id)
        .order_by(ProcessStep.step_order, ProcessStep.id)
        .execution_options(populate_existing=True)
    )
    steps = [
        ProcessStepOut(
            id=step.id,
            step_order=step.step_order,
            title=step.title,
            description=step.description,
            default_category=LookupRef.model_validate(category) if category else None,
            estimated_hours=step.estimated_hours,
        )
        for step, category in rows.all()
    ]
    counts = (await _counts(db, [process.id]))[process.id]
    return ProcessOut(**_list_item(process, counts).model_dump(), steps=steps)


async def _check_category(
    db: AsyncSession, value: int | None, keep: int | None, error_field: str
) -> None:
    if value is not None:
        await check_ref(db, "category_id", value, keep=keep, error_field=error_field)


def _touch(process: Process) -> None:
    """Steps live in their own table, so mark the process itself as changed."""
    process.updated_at = utcnow()


# ---------------------------------------------------------------- reads


async def list_processes(
    db: AsyncSession, user: User, params: ProcessQuery
) -> Page[ProcessListItem]:
    stmt = select(Process).where(Process.owner_id == user.id)
    if params.is_active is not None:
        stmt = stmt.where(Process.is_active == params.is_active)
    stmt = stmt.order_by(Process.is_active.desc(), func.lower(Process.name), Process.id)
    processes, total = await paginate(db, stmt, params)
    counts = await _counts(db, [p.id for p in processes])
    items = [_list_item(p, counts[p.id]) for p in processes]
    return Page[ProcessListItem].build(items, total, params)


async def get_process(db: AsyncSession, user: User, process_id: int) -> ProcessOut:
    return await _load(db, await get_own(db, user, process_id, lock=False))


# ---------------------------------------------------------------- process writes


async def create_process(db: AsyncSession, user: User, data: ProcessCreate) -> ProcessOut:
    for index, step in enumerate(data.steps):
        await _check_category(
            db, step.default_category_id, None, f"steps.{index}.default_category_id"
        )
    process = Process(owner_id=user.id, name=data.name, description=data.description or None)
    db.add(process)
    await db.flush()
    db.add_all(
        ProcessStep(
            process_id=process.id,
            step_order=order,
            title=step.title,
            description=step.description or None,
            default_category_id=step.default_category_id,
            estimated_hours=step.estimated_hours,
        )
        for order, step in enumerate(data.steps)
    )
    await db.commit()
    logger.info("process_created", extra={"fields": {"process_id": process.id}})
    return await _load(db, process)


async def update_process(
    db: AsyncSession, user: User, process_id: int, data: ProcessUpdate
) -> ProcessOut:
    process = await get_own(db, user, process_id, lock=True)
    sent = data.model_fields_set
    if "name" in sent and data.name is not None:
        process.name = data.name
    if "description" in sent:
        process.description = data.description or None
    await db.commit()
    return await _load(db, process)


async def set_active(db: AsyncSession, user: User, process_id: int, active: bool) -> ProcessOut:
    """Deactivated processes stay visible (with their runs) but cannot start new runs."""
    process = await get_own(db, user, process_id, lock=True)
    process.is_active = active
    await db.commit()
    logger.info(
        "process_activated" if active else "process_deactivated",
        extra={"fields": {"process_id": process.id}},
    )
    return await _load(db, process)


async def delete_process(db: AsyncSession, user: User, process_id: int) -> None:
    """Only while the process has no runs. Its steps go with it (CASCADE)."""
    process = await get_own(db, user, process_id, lock=True)
    has_runs = await db.scalar(select(ProcessRun.id).where(ProcessRun.process_id == process.id))
    if has_runs is not None:
        raise AppError(
            409,
            "process_has_runs",
            "This process has runs, so it cannot be deleted. Deactivate it instead.",
        )
    await db.delete(process)
    await db.commit()
    logger.info("process_deleted", extra={"fields": {"process_id": process_id}})


# ---------------------------------------------------------------- step writes


async def add_step(db: AsyncSession, user: User, process_id: int, data: StepCreate) -> ProcessOut:
    """Appends the step at the end of the process."""
    process = await get_own(db, user, process_id, lock=True)
    await _check_category(db, data.default_category_id, None, "default_category_id")
    existing = await steps_in_order(db, process.id)
    if len(existing) >= MAX_STEPS:
        message = f"A process can have at most {MAX_STEPS} steps"
        raise AppError(422, "too_many_steps", message, fields={"title": message})
    _renumber(existing)
    db.add(
        ProcessStep(
            process_id=process.id,
            step_order=len(existing),
            title=data.title,
            description=data.description or None,
            default_category_id=data.default_category_id,
            estimated_hours=data.estimated_hours,
        )
    )
    _touch(process)
    await db.commit()
    return await _load(db, process)


async def update_step(
    db: AsyncSession, user: User, process_id: int, step_id: int, data: StepUpdate
) -> ProcessOut:
    process = await get_own(db, user, process_id, lock=True)
    step = await _get_step(db, process, step_id)
    sent = data.model_fields_set
    if "default_category_id" in sent:
        await _check_category(
            db, data.default_category_id, step.default_category_id, "default_category_id"
        )
        step.default_category_id = data.default_category_id
    if "title" in sent and data.title is not None:
        step.title = data.title
    if "description" in sent:
        step.description = data.description or None
    if "estimated_hours" in sent:
        step.estimated_hours = data.estimated_hours
    _touch(process)
    await db.commit()
    return await _load(db, process)


async def delete_step(db: AsyncSession, user: User, process_id: int, step_id: int) -> None:
    process = await get_own(db, user, process_id, lock=True)
    step = await _get_step(db, process, step_id)
    await db.delete(step)
    await db.flush()
    _renumber(await steps_in_order(db, process.id))
    _touch(process)
    await db.commit()


async def reorder_steps(
    db: AsyncSession, user: User, process_id: int, data: StepOrder
) -> ProcessOut:
    process = await get_own(db, user, process_id, lock=True)
    by_id = {step.id: step for step in await steps_in_order(db, process.id)}
    if set(data.step_ids) != set(by_id):
        message = "List every step of the process exactly once"
        raise AppError(422, "invalid_order", message, fields={"step_ids": message})
    _renumber([by_id[step_id] for step_id in data.step_ids])
    _touch(process)
    await db.commit()
    return await _load(db, process)


async def sync_steps(db: AsyncSession, user: User, process_id: int, data: StepsSync) -> ProcessOut:
    """Makes the process's steps match `data.steps` in one transaction: steps with an
    id are updated, steps without one are added, existing steps left out are deleted.
    Used by the edit form's step editor."""
    process = await get_own(db, user, process_id, lock=True)
    by_id = {step.id: step for step in await steps_in_order(db, process.id)}

    for index, item in enumerate(data.steps):
        if item.id is not None and item.id not in by_id:
            raise AppError(
                422,
                "invalid_reference",
                "Step not found in this process",
                fields={f"steps.{index}.id": "Step not found in this process"},
            )
        keep = by_id[item.id].default_category_id if item.id is not None else None
        await _check_category(
            db, item.default_category_id, keep, f"steps.{index}.default_category_id"
        )

    kept = {item.id for item in data.steps if item.id is not None}
    for step_id, step in by_id.items():
        if step_id not in kept:
            await db.delete(step)

    for order, item in enumerate(data.steps):
        step = by_id[item.id] if item.id is not None else ProcessStep(process_id=process.id)
        step.step_order = order
        step.title = item.title
        step.description = item.description or None
        step.default_category_id = item.default_category_id
        step.estimated_hours = item.estimated_hours
        if item.id is None:
            db.add(step)

    _touch(process)
    await db.commit()
    logger.info(
        "process_steps_synced",
        extra={"fields": {"process_id": process.id, "steps": len(data.steps)}},
    )
    return await _load(db, process)
