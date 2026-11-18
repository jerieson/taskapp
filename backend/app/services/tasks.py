"""Tasks. Every user (admin included) sees and changes only their own tasks.

Rules enforced here:
- A task someone else owns is reported as 404, never 403.
- New tasks without a status/priority get the default one (found by `is_default`).
- Moving to a status with `is_done` sets `completed_at`; moving to a status without it
  clears `completed_at`. Moving between two done statuses keeps the original time.
- Changing the status of (or deleting) a task from a process run updates the run's
  status (see `services.run_status`).
- Create accepts only active dropdown values and projects. Update also accepts the
  value already on the task, even if it has since been deactivated.
"""

import logging
from datetime import date, datetime

from sqlalchemy import Row, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.pagination import Page
from app.db.base import utcnow
from app.models import Category, Priority, Project, Status, Task, User
from app.schemas.tasks import (
    LookupRef,
    ProjectRef,
    StatusRef,
    TaskCreate,
    TaskOut,
    TaskQuery,
    TaskSort,
    TaskState,
    TaskUpdate,
)
from app.services.refs import check_ref
from app.services.run_status import sync_run_status

logger = logging.getLogger("app.tasks")

_TaskRow = tuple[Task, Status, Priority, Category | None, Project | None]


def task_query() -> Select[_TaskRow]:
    return (
        select(Task, Status, Priority, Category, Project)
        .join(Status, Status.id == Task.status_id)
        .join(Priority, Priority.id == Task.priority_id)
        .outerjoin(Category, Category.id == Task.category_id)
        .outerjoin(Project, Project.id == Task.project_id)
    )


def task_out(row: Row[_TaskRow], today: date) -> TaskOut:
    task, status, priority, category, project = row
    return TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        project=ProjectRef.model_validate(project) if project else None,
        category=LookupRef.model_validate(category) if category else None,
        status=StatusRef.model_validate(status),
        priority=LookupRef.model_validate(priority),
        due_date=task.due_date,
        completed_at=task.completed_at,
        is_overdue=task.due_date is not None and task.due_date < today and not status.is_done,
        process_run_id=task.process_run_id,
        process_step_id=task.process_step_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


async def _load(db: AsyncSession, user: User, task_id: int, today: date) -> TaskOut:
    row = (
        await db.execute(
            task_query()
            .where(Task.id == task_id, Task.user_id == user.id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None:
        raise _not_found()
    return task_out(row, today)


def _not_found() -> AppError:
    return AppError(404, "not_found", "Task not found")


async def _get_own(db: AsyncSession, user: User, task_id: int) -> Task:
    """The caller's task, or 404 (also when it exists but belongs to someone else)."""
    task = await db.scalar(
        select(Task).where(Task.id == task_id, Task.user_id == user.id).with_for_update()
    )
    if task is None:
        raise _not_found()
    return task


async def default_id(db: AsyncSession, model: type[Status] | type[Priority], noun: str) -> int:
    row_id = await db.scalar(select(model.id).where(model.is_default, model.is_active))
    if row_id is None:
        raise AppError(
            409,
            f"no_default_{noun}",
            f"No default {noun} is set. Ask an admin to set one, or choose a {noun}.",
        )
    return row_id


def apply_status(task: Task, status: Status, was_done: bool, now: datetime) -> None:
    if status.is_done and not was_done:
        task.completed_at = now
    elif not status.is_done:
        task.completed_at = None


# ---------------------------------------------------------------- queries

# Tasks without a due date always sort last. The admin orders priorities from lowest
# to highest (the seed's order), so a higher sort_order means a higher priority.
_ORDER = {
    TaskSort.DUE_DATE: (Task.due_date.asc().nulls_last(), Priority.sort_order.desc()),
    TaskSort.DUE_DATE_DESC: (Task.due_date.desc().nulls_last(), Priority.sort_order.desc()),
    TaskSort.PRIORITY: (Priority.sort_order.desc(), Task.due_date.asc().nulls_last()),
    TaskSort.PRIORITY_DESC: (Priority.sort_order.asc(), Task.due_date.asc().nulls_last()),
    TaskSort.CREATED: (Task.created_at.asc(),),
    TaskSort.CREATED_DESC: (Task.created_at.desc(),),
}


async def list_tasks(db: AsyncSession, user: User, params: TaskQuery, today: date) -> Page[TaskOut]:
    stmt = task_query().where(Task.user_id == user.id)
    for field in ("status_id", "priority_id", "project_id", "category_id", "process_run_id"):
        value = getattr(params, field)
        if value is not None:
            stmt = stmt.where(getattr(Task, field) == value)
    if params.due_from is not None:
        stmt = stmt.where(Task.due_date >= params.due_from)
    if params.due_to is not None:
        stmt = stmt.where(Task.due_date <= params.due_to)
    if params.state == TaskState.OPEN:
        stmt = stmt.where(~Status.is_done)
    elif params.state == TaskState.COMPLETED:
        stmt = stmt.where(Status.is_done)
    if params.in_process_run is True:
        stmt = stmt.where(Task.process_run_id.is_not(None))
    elif params.in_process_run is False:
        stmt = stmt.where(Task.process_run_id.is_(None))

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.execute(
        stmt.order_by(*_ORDER[params.sort], Task.id.desc())
        .limit(params.limit)
        .offset(params.offset)
    )
    return Page[TaskOut].build([task_out(r, today) for r in rows.all()], total, params)


async def get_task(db: AsyncSession, user: User, task_id: int, today: date) -> TaskOut:
    return await _load(db, user, task_id, today)


# ---------------------------------------------------------------- writes

_TASK_REFS = ("status_id", "priority_id", "category_id", "project_id")


async def create_task(db: AsyncSession, user: User, data: TaskCreate, today: date) -> TaskOut:
    for field in _TASK_REFS:
        value = getattr(data, field)
        if value is not None:
            await check_ref(db, field, value, keep=None)
    status_id = data.status_id or await default_id(db, Status, "status")
    priority_id = data.priority_id or await default_id(db, Priority, "priority")
    status = await db.get_one(Status, status_id)

    task = Task(
        user_id=user.id,
        title=data.title,
        description=data.description or None,
        project_id=data.project_id,
        category_id=data.category_id,
        status_id=status_id,
        priority_id=priority_id,
        due_date=data.due_date,
    )
    apply_status(task, status, was_done=False, now=utcnow())
    db.add(task)
    await db.commit()
    logger.info("task_created", extra={"fields": {"task_id": task.id}})
    return await _load(db, user, task.id, today)


async def update_task(
    db: AsyncSession, user: User, task_id: int, data: TaskUpdate, today: date
) -> TaskOut:
    task = await _get_own(db, user, task_id)
    sent = data.model_fields_set

    for field in _TASK_REFS:
        if field in sent:
            value = getattr(data, field)
            if value is not None:
                await check_ref(db, field, value, keep=getattr(task, field))

    if "status_id" in sent and data.status_id != task.status_id:
        old = await db.get_one(Status, task.status_id)
        new = await db.get_one(Status, data.status_id)
        apply_status(task, new, was_done=old.is_done, now=utcnow())
        status_changed = True
    else:
        status_changed = False

    for field in ("title", "status_id", "priority_id", "project_id", "category_id", "due_date"):
        if field in sent:
            setattr(task, field, getattr(data, field))
    if "description" in sent:
        task.description = data.description or None

    if status_changed and task.process_run_id is not None:
        await sync_run_status(db, task.process_run_id)
    await db.commit()
    logger.info("task_updated", extra={"fields": {"task_id": task.id}})
    return await _load(db, user, task.id, today)


async def delete_task(db: AsyncSession, user: User, task_id: int) -> None:
    """Prod logs keep their data (task_id SET NULL); daily plan items go (CASCADE).

    Deleting a run's last open task can complete the run."""
    task = await _get_own(db, user, task_id)
    run_id = task.process_run_id
    await db.delete(task)
    if run_id is not None:
        await sync_run_status(db, run_id)
    await db.commit()
    logger.info("task_deleted", extra={"fields": {"task_id": task_id}})
