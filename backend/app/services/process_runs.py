"""Process runs. Every user (admin included) sees and changes only their own runs.

Rules enforced here:
- A run (or process) someone else owns is reported as 404, never 403.
- Starting a run copies every step into a new task in one transaction: title,
  description, the step's default category (left empty if it has been deactivated
  since), the default status and priority, `process_run_id` and `process_step_id`,
  plus an optional due date for all of them. Later template edits never change them.
- Only active processes with at least one step can start a run.
- Runs are never deleted. Cancelling keeps the tasks; a cancelled run stays cancelled.
- Completion follows the tasks automatically (see `services.run_status`).
"""

import logging
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.pagination import Page, paginate
from app.db.base import utcnow
from app.models import Category, Priority, Process, ProcessRun, RunStatus, Status, Task, User
from app.schemas.processes import (
    ProcessRef,
    RunCreate,
    RunDetail,
    RunOut,
    RunProgress,
    RunQuery,
)
from app.services import processes
from app.services.run_status import sync_run_status
from app.services.tasks import apply_status, default_id, task_out, task_query

logger = logging.getLogger("app.process_runs")


def _not_found() -> AppError:
    return AppError(404, "not_found", "Run not found")


async def _progress(db: AsyncSession, run_ids: list[int]) -> dict[int, RunProgress]:
    if not run_ids:
        return {}
    rows = await db.execute(
        select(Task.process_run_id, func.count().filter(Status.is_done), func.count())
        .join(Status, Status.id == Task.status_id)
        .where(Task.process_run_id.in_(run_ids))
        .group_by(Task.process_run_id)
    )
    found = {run_id: RunProgress(done=done, total=total) for run_id, done, total in rows.all()}
    return {run_id: found.get(run_id, RunProgress(done=0, total=0)) for run_id in run_ids}


def _run_out(run: ProcessRun, process: Process, progress: RunProgress) -> RunOut:
    return RunOut(
        id=run.id,
        process=ProcessRef(id=process.id, name=process.name, is_active=process.is_active),
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        progress=progress,
    )


async def _get_own(db: AsyncSession, user: User, run_id: int, *, lock: bool) -> ProcessRun:
    stmt = select(ProcessRun).where(ProcessRun.id == run_id, ProcessRun.user_id == user.id)
    if lock:
        stmt = stmt.with_for_update()
    run = await db.scalar(stmt)
    if run is None:
        raise _not_found()
    return run


async def _detail(db: AsyncSession, user: User, run: ProcessRun, today: date) -> RunDetail:
    await db.refresh(run)
    process = await db.get_one(Process, run.process_id, populate_existing=True)
    rows = await db.execute(
        task_query()
        .where(Task.process_run_id == run.id, Task.user_id == user.id)
        .order_by(Task.id)
        .execution_options(populate_existing=True)
    )
    tasks = [task_out(row, today) for row in rows.all()]
    progress = RunProgress(done=sum(t.status.is_done for t in tasks), total=len(tasks))
    return RunDetail(**_run_out(run, process, progress).model_dump(), tasks=tasks)


# ---------------------------------------------------------------- reads


async def list_runs(
    db: AsyncSession, user: User, process_id: int, params: RunQuery
) -> Page[RunOut]:
    """Runs of one of the caller's processes, newest first."""
    process = await processes.get_own(db, user, process_id, lock=False)
    stmt = select(ProcessRun).where(
        ProcessRun.process_id == process.id, ProcessRun.user_id == user.id
    )
    if params.status is not None:
        stmt = stmt.where(ProcessRun.status == params.status)
    stmt = stmt.order_by(ProcessRun.started_at.desc(), ProcessRun.id.desc())
    runs, total = await paginate(db, stmt, params)
    progress = await _progress(db, [run.id for run in runs])
    items = [_run_out(run, process, progress[run.id]) for run in runs]
    return Page[RunOut].build(items, total, params)


async def get_run(db: AsyncSession, user: User, run_id: int, today: date) -> RunDetail:
    return await _detail(db, user, await _get_own(db, user, run_id, lock=False), today)


# ---------------------------------------------------------------- writes


async def start_run(
    db: AsyncSession, user: User, process_id: int, data: RunCreate, today: date
) -> RunDetail:
    process = await processes.get_own(db, user, process_id, lock=True)
    if not process.is_active:
        raise AppError(409, "process_inactive", "Activate this process before starting a run.")
    steps = await processes.steps_in_order(db, process.id)
    if not steps:
        raise AppError(409, "process_has_no_steps", "Add at least one step before starting a run.")

    status_id = await default_id(db, Status, "status")
    priority_id = await default_id(db, Priority, "priority")
    status = await db.get_one(Status, status_id)
    category_ids = {s.default_category_id for s in steps if s.default_category_id is not None}
    active_categories = set(
        (
            await db.scalars(
                select(Category.id).where(Category.id.in_(category_ids), Category.is_active)
            )
        ).all()
    )

    run = ProcessRun(process_id=process.id, user_id=user.id, status=RunStatus.IN_PROGRESS)
    db.add(run)
    await db.flush()
    now = utcnow()
    for step in steps:
        task = Task(
            user_id=user.id,
            title=step.title,
            description=step.description,
            category_id=(
                step.default_category_id if step.default_category_id in active_categories else None
            ),
            status_id=status_id,
            priority_id=priority_id,
            due_date=data.due_date,
            process_run_id=run.id,
            process_step_id=step.id,
        )
        apply_status(task, status, was_done=False, now=now)
        db.add(task)
    # Only matters if the default status itself counts as done.
    await sync_run_status(db, run.id)
    await db.commit()
    logger.info(
        "run_started",
        extra={"fields": {"run_id": run.id, "process_id": process.id, "tasks": len(steps)}},
    )
    return await _detail(db, user, run, today)


async def cancel_run(db: AsyncSession, user: User, run_id: int, today: date) -> RunDetail:
    """Only runs in progress can be cancelled. The run's tasks are kept unchanged."""
    run = await _get_own(db, user, run_id, lock=True)
    if run.status != RunStatus.IN_PROGRESS:
        raise AppError(409, "run_not_in_progress", "Only a run in progress can be cancelled.")
    run.status = RunStatus.CANCELLED
    await db.commit()
    logger.info("run_cancelled", extra={"fields": {"run_id": run.id}})
    return await _detail(db, user, run, today)
