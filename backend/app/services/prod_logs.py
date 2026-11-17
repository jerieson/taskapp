"""Prod logs and the team view of them.

Access (see the permission matrix in CLAUDE.md):
- Everyone creates, reads, changes and deletes their own logs.
- Admins can read, change and delete any log.
- Managers can read logs whose team snapshot (`prod_logs.team_id`) is their team, but
  cannot change them. Devs cannot see anyone else's logs.
- A log the caller may not see is reported as 404. A manager trying to change a log
  they can see gets 403.

Rules enforced here:
- `team_id` is copied from the author's team on create and never changes.
- `updated_by` is the caller on every create and update.
- A linked task must belong to the log's author. Its project/category are copied onto a
  new log when those are omitted.
- The author's total hours on one date may not exceed 24.
- Only active categories/projects can be chosen; on update the current value may stay.
"""

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import Row, Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import AppError
from app.core.pagination import Page, PaginationParams
from app.models import Category, ProdLog, Project, Role, Task, Team, User
from app.schemas.prod_logs import (
    MAX_DAILY_HOURS,
    ProdLogCreate,
    ProdLogListItem,
    ProdLogOut,
    ProdLogQuery,
    ProdLogUpdate,
    TaskRef,
    TeamLogQuery,
    TeamMemberOut,
    UserRef,
)
from app.schemas.tasks import LookupRef, ProjectRef
from app.services.refs import check_ref, invalid_reference

logger = logging.getLogger("app.prod_logs")

Author = aliased(User, name="author")
Editor = aliased(User, name="editor")

_LogRow = tuple[ProdLog, Category, Project | None, User, User, int | None, str | None]


def _base_query() -> Select[_LogRow]:
    return (
        select(ProdLog, Category, Project, Author, Editor, Task.id, Task.title)
        .join(Category, Category.id == ProdLog.category_id)
        .outerjoin(Project, Project.id == ProdLog.project_id)
        .join(Author, Author.id == ProdLog.user_id)
        .join(Editor, Editor.id == ProdLog.updated_by)
        .outerjoin(Task, Task.id == ProdLog.task_id)
    )


def _fields(row: Row[Any], viewer: User) -> dict[str, Any]:
    log, category, project, author, editor, task_id, task_title = row[:7]
    show_task = task_id is not None and log.user_id == viewer.id
    return {
        "id": log.id,
        "user": UserRef.model_validate(author),
        "team_id": log.team_id,
        "log_date": log.log_date,
        "title": log.title,
        "description": log.description,
        "task_id": log.task_id,
        "task": TaskRef(id=task_id, title=task_title) if show_task else None,
        "project": ProjectRef.model_validate(project) if project else None,
        "category": LookupRef.model_validate(category),
        "hours_spent": log.hours_spent,
        "updated_by": UserRef.model_validate(editor),
        "created_at": log.created_at,
        "updated_at": log.updated_at,
    }


def _not_found() -> AppError:
    return AppError(404, "not_found", "Log not found")


def _can_read(user: User, log: ProdLog) -> bool:
    if log.user_id == user.id or user.role == Role.ADMIN:
        return True
    return user.role == Role.MANAGER and log.team_id is not None and log.team_id == user.team_id


async def _load(db: AsyncSession, user: User, log_id: int) -> ProdLogOut:
    row = (
        await db.execute(
            _base_query().where(ProdLog.id == log_id).execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None or not _can_read(user, row[0]):
        raise _not_found()
    return ProdLogOut.model_validate(_fields(row, user))


async def _get_writable(db: AsyncSession, user: User, log_id: int) -> ProdLog:
    """A log the caller may change: their own, or any log for an admin."""
    log = await db.scalar(select(ProdLog).where(ProdLog.id == log_id).with_for_update())
    if log is None or not _can_read(user, log):
        raise _not_found()
    if log.user_id != user.id and user.role != Role.ADMIN:
        raise AppError(403, "forbidden", "You can view this log but not change it")
    return log


async def _check_task(db: AsyncSession, task_id: int, author_id: int) -> Task:
    task = await db.get(Task, task_id)
    if task is None or task.user_id != author_id:
        raise invalid_reference("task_id", "Choose one of the author's own tasks")
    return task


async def _check_daily_total(
    db: AsyncSession, log: ProdLog, hours: Decimal, exclude_id: int | None
) -> None:
    """Reject if the author's logs on `log.log_date` would total more than 24 hours.

    An advisory lock per author serialises concurrent writes, so two requests cannot
    both pass the check and together exceed the cap.
    """
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"prod_logs:user:{log.user_id}"},
    )
    stmt = select(func.coalesce(func.sum(ProdLog.hours_spent), 0)).where(
        ProdLog.user_id == log.user_id, ProdLog.log_date == log.log_date
    )
    if exclude_id is not None:
        stmt = stmt.where(ProdLog.id != exclude_id)
    others = Decimal(await db.scalar(stmt) or 0)
    if others + hours > MAX_DAILY_HOURS:
        left = max(MAX_DAILY_HOURS - others, Decimal(0))
        message = f"Max {MAX_DAILY_HOURS:g} h per day: {others:g} h already logged, {left:g} h left"
        raise AppError(422, "daily_hours_exceeded", message, fields={"hours_spent": message})


async def _active_or_none(db: AsyncSession, field: str, value: int | None) -> int | None:
    """`value` if it is set and active, else None (used when copying from a task)."""
    if value is None:
        return None
    try:
        await check_ref(db, field, value, keep=None)
    except AppError:
        return None
    return value


# ---------------------------------------------------------------- lists


async def _page(
    db: AsyncSession, stmt: Select[_LogRow], params: PaginationParams, viewer: User
) -> Page[ProdLogListItem]:
    day_total = func.sum(ProdLog.hours_spent).over(partition_by=ProdLog.log_date)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.execute(
        stmt.add_columns(day_total)
        .order_by(ProdLog.log_date.desc(), ProdLog.created_at.desc(), ProdLog.id.desc())
        .limit(params.limit)
        .offset(params.offset)
    )
    items = [
        ProdLogListItem.model_validate({**_fields(row, viewer), "day_total_hours": row[7]})
        for row in rows.all()
    ]
    return Page[ProdLogListItem].build(items, total, params)


def _filter(stmt: Select[_LogRow], params: ProdLogQuery | TeamLogQuery) -> Select[_LogRow]:
    if params.date_from is not None:
        stmt = stmt.where(ProdLog.log_date >= params.date_from)
    if params.date_to is not None:
        stmt = stmt.where(ProdLog.log_date <= params.date_to)
    if params.project_id is not None:
        stmt = stmt.where(ProdLog.project_id == params.project_id)
    if params.category_id is not None:
        stmt = stmt.where(ProdLog.category_id == params.category_id)
    return stmt


async def list_logs(db: AsyncSession, user: User, params: ProdLogQuery) -> Page[ProdLogListItem]:
    """The caller's own logs (for admins too: other people's logs are under /teams)."""
    stmt = _filter(_base_query().where(ProdLog.user_id == user.id), params)
    if params.task_id is not None:
        stmt = stmt.where(ProdLog.task_id == params.task_id)
    return await _page(db, stmt, params, user)


async def _check_team_access(db: AsyncSession, user: User, team_id: int) -> None:
    """Admins: any existing team. Managers: their own team only (404 for others).
    Devs: no team access at all."""
    if user.role == Role.DEV:
        raise AppError(403, "forbidden", "Only managers and admins can view team logs")
    if user.role == Role.MANAGER and user.team_id != team_id:
        raise AppError(404, "not_found", "Team not found")
    if await db.get(Team, team_id) is None:
        raise AppError(404, "not_found", "Team not found")


async def list_team_logs(
    db: AsyncSession, user: User, team_id: int, params: TeamLogQuery
) -> Page[ProdLogListItem]:
    """Logs whose team snapshot is `team_id`, whatever team the author is in now."""
    await _check_team_access(db, user, team_id)
    stmt = _filter(_base_query().where(ProdLog.team_id == team_id), params)
    if params.user_id is not None:
        stmt = stmt.where(ProdLog.user_id == params.user_id)
    return await _page(db, stmt, params, user)


async def list_team_members(
    db: AsyncSession, user: User, team_id: int, params: PaginationParams
) -> Page[TeamMemberOut]:
    """Current members plus former members who have logs under this team."""
    await _check_team_access(db, user, team_id)
    former = select(ProdLog.user_id).where(ProdLog.team_id == team_id)
    stmt = select(User).where((User.team_id == team_id) | User.id.in_(former))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    users = await db.scalars(
        stmt.order_by(func.lower(User.username)).limit(params.limit).offset(params.offset)
    )
    items = [
        TeamMemberOut(
            id=u.id,
            username=u.username,
            is_active=u.is_active,
            is_current_member=u.team_id == team_id,
        )
        for u in users.all()
    ]
    return Page[TeamMemberOut].build(items, total, params)


# ---------------------------------------------------------------- single log


async def get_log(db: AsyncSession, user: User, log_id: int) -> ProdLogOut:
    return await _load(db, user, log_id)


async def create_log(db: AsyncSession, user: User, data: ProdLogCreate) -> ProdLogOut:
    sent = data.model_fields_set
    project_id, category_id = data.project_id, data.category_id
    if data.task_id is not None:
        task = await _check_task(db, data.task_id, user.id)
        if "project_id" not in sent:
            project_id = await _active_or_none(db, "project_id", task.project_id)
        if category_id is None:
            category_id = await _active_or_none(db, "category_id", task.category_id)
    if category_id is None:
        raise invalid_reference("category_id", "Choose a category")
    await check_ref(db, "category_id", category_id, keep=None)
    if project_id is not None:
        await check_ref(db, "project_id", project_id, keep=None)

    log = ProdLog(
        user_id=user.id,
        team_id=user.team_id,
        task_id=data.task_id,
        log_date=data.log_date,
        title=data.title,
        description=data.description or None,
        project_id=project_id,
        category_id=category_id,
        hours_spent=data.hours_spent,
        updated_by=user.id,
    )
    await _check_daily_total(db, log, data.hours_spent, exclude_id=None)
    db.add(log)
    await db.commit()
    logger.info("prod_log_created", extra={"fields": {"log_id": log.id}})
    return await _load(db, user, log.id)


async def update_log(db: AsyncSession, user: User, log_id: int, data: ProdLogUpdate) -> ProdLogOut:
    log = await _get_writable(db, user, log_id)
    sent = data.model_fields_set

    for field in ("category_id", "project_id"):
        value = getattr(data, field)
        if field in sent and value is not None:
            await check_ref(db, field, value, keep=getattr(log, field))
    if "task_id" in sent and data.task_id is not None and data.task_id != log.task_id:
        await _check_task(db, data.task_id, log.user_id)

    for field in ("log_date", "title", "hours_spent", "task_id", "project_id", "category_id"):
        if field in sent:
            setattr(log, field, getattr(data, field))
    if "description" in sent:
        log.description = data.description or None
    if sent & {"log_date", "hours_spent"}:
        await _check_daily_total(db, log, log.hours_spent, exclude_id=log.id)
    log.updated_by = user.id

    await db.commit()
    logger.info("prod_log_updated", extra={"fields": {"log_id": log.id}})
    return await _load(db, user, log.id)


async def delete_log(db: AsyncSession, user: User, log_id: int) -> None:
    log = await _get_writable(db, user, log_id)
    await db.delete(log)
    await db.commit()
    logger.info("prod_log_deleted", extra={"fields": {"log_id": log_id}})
