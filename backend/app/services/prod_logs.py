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
- New rows need a category, project, activity and work set-up (the default one when
  omitted), and planned hours, actual hours or both.
- Linked dropdowns: the project must be linked to the category, the activity must be in
  the project's activity group, and an O&M project is only allowed when the category
  offers one. On update, a pair that is unchanged may stay even if the admin has since
  removed the link.
- The author's total actual hours on one date may not exceed WORKDAY_HOURS, and
  separately their total planned hours.
- Only active values can be chosen; on update the current value may stay.
- Planned/Unplanned is the user's choice (Planned by default).
- Weekly planning (app/core/weeks.py): in a locked week planned hours cannot be set,
  changed or cleared and rows with planned hours cannot be deleted (422
  `week_locked`). Admins are exempt.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Row, Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, aliased

from app.core.config import Settings
from app.core.errors import AppError
from app.core.pagination import Page, PaginationParams
from app.core.weeks import PlanWeek, monday_of, plan_week
from app.models import (
    Activity,
    ActivityGroupMember,
    Category,
    DeviationReason,
    OmProject,
    ProdLog,
    Project,
    Role,
    Task,
    Team,
    User,
    WorkSetup,
)
from app.schemas.prod_logs import (
    CopyDayResult,
    CopyLogs,
    CopyResult,
    PlainRef,
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

_LogRow = tuple[
    ProdLog,
    Category,
    Project | None,
    User,
    User,
    WorkSetup,
    Activity,
    OmProject | None,
    DeviationReason | None,
    int | None,
    str | None,
]
_ROW_LEN = 11


def _base_query() -> Select[_LogRow]:
    return (
        select(
            ProdLog,
            Category,
            Project,
            Author,
            Editor,
            WorkSetup,
            Activity,
            OmProject,
            DeviationReason,
            Task.id,
            Task.title,
        )
        .join(Category, Category.id == ProdLog.category_id)
        .outerjoin(Project, Project.id == ProdLog.project_id)
        .join(Author, Author.id == ProdLog.user_id)
        .join(Editor, Editor.id == ProdLog.updated_by)
        .join(WorkSetup, WorkSetup.id == ProdLog.work_setup_id)
        .join(Activity, Activity.id == ProdLog.activity_id)
        .outerjoin(OmProject, OmProject.id == ProdLog.om_project_id)
        .outerjoin(DeviationReason, DeviationReason.id == ProdLog.deviation_reason_id)
        .outerjoin(Task, Task.id == ProdLog.task_id)
    )


def _fields(row: Row[Any], viewer: User) -> dict[str, Any]:
    (
        log,
        category,
        project,
        author,
        editor,
        work_setup,
        activity,
        om_project,
        deviation_reason,
        task_id,
        task_title,
    ) = row[:_ROW_LEN]
    show_task = task_id is not None and log.user_id == viewer.id
    return {
        "id": log.id,
        "user": UserRef.model_validate(author),
        "team_id": log.team_id,
        "log_date": log.log_date,
        "work_setup": LookupRef.model_validate(work_setup),
        "is_planned": log.is_planned,
        "planned_hours": log.planned_hours,
        "hours_spent": log.hours_spent,
        "category": LookupRef.model_validate(category),
        "project": ProjectRef.model_validate(project) if project else None,
        "activity": LookupRef.model_validate(activity),
        "om_project": PlainRef.model_validate(om_project) if om_project else None,
        "task_id": log.task_id,
        "task": TaskRef(id=task_id, title=task_title) if show_task else None,
        "title": log.title,
        "description": log.description,
        "deviation_reason": PlainRef.model_validate(deviation_reason) if deviation_reason else None,
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


async def _default_work_setup(db: AsyncSession) -> int:
    row_id = await db.scalar(select(WorkSetup.id).where(WorkSetup.is_default, WorkSetup.is_active))
    if row_id is None:
        raise AppError(
            409,
            "no_default_work_setup",
            "No default work set-up is set. Ask an admin to set one, or choose a work set-up.",
        )
    return row_id


def _week_locked(week: PlanWeek, field: str | None, what: str) -> AppError:
    deadline = week.deadline.strftime("%a %d %b, %H:%M")
    message = f"Planning for the week of {week.start:%d %b} closed on {deadline}: {what}"
    return AppError(422, "week_locked", message, fields={field: message} if field else None)


def _hours_required() -> AppError:
    message = "Enter planned hours, actual hours, or both"
    return AppError(422, "hours_required", message, fields={"hours_spent": message})


# ---------------------------------------------------------------- linked dropdowns


@dataclass(frozen=True)
class _Links:
    category_id: int
    project_id: int | None
    activity_id: int
    om_project_id: int | None


async def _check_links(db: AsyncSession, new: _Links, old: _Links | None = None) -> None:
    """The project is linked to the category, the activity is in the project's group,
    and an O&M project is only set when the category offers one.

    `old` holds the values already on the log: a pair that is unchanged is not checked
    again, so a row stays editable after the admin changes the links.
    """

    def unchanged(*names: str) -> bool:
        return old is not None and all(getattr(new, n) == getattr(old, n) for n in names)

    category = await db.get(Category, new.category_id)
    project = await db.get(Project, new.project_id) if new.project_id is not None else None
    if (
        project is not None
        and not unchanged("category_id", "project_id")
        and new.category_id not in project.category_ids
    ):
        raise invalid_reference("project_id", "Choose a project under the chosen category")
    if project is not None and not unchanged("project_id", "activity_id"):
        in_group = project.activity_group_id is not None and await db.scalar(
            select(ActivityGroupMember.activity_id).where(
                ActivityGroupMember.activity_group_id == project.activity_group_id,
                ActivityGroupMember.activity_id == new.activity_id,
            )
        )
        if not in_group:
            raise invalid_reference("activity_id", "Choose an activity offered for this project")
    offers_om = category is not None and category.requires_om_project
    if (
        new.om_project_id is not None
        and not offers_om
        and not unchanged("category_id", "om_project_id")
    ):
        raise invalid_reference(
            "om_project_id", "Project (For O&M) is only for categories that offer it"
        )


def _links_of(log: ProdLog) -> _Links:
    return _Links(log.category_id, log.project_id, log.activity_id, log.om_project_id)


# ---------------------------------------------------------------- daily caps


async def _check_daily_total(
    db: AsyncSession,
    log: ProdLog,
    column: InstrumentedAttribute[Decimal | None],
    hours: Decimal | None,
    exclude_id: int | None,
    cap: Decimal,
) -> None:
    """Reject if the author's `column` hours on `log.log_date` would total more than
    `cap` (WORKDAY_HOURS).

    Actual and planned hours are capped separately. An advisory lock per author
    serialises concurrent writes, so two requests cannot both pass the check and
    together exceed the cap.
    """
    if hours is None:
        return
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"prod_logs:user:{log.user_id}"},
    )
    stmt = select(func.coalesce(func.sum(column), 0)).where(
        ProdLog.user_id == log.user_id, ProdLog.log_date == log.log_date
    )
    if exclude_id is not None:
        stmt = stmt.where(ProdLog.id != exclude_id)
    others = Decimal(await db.scalar(stmt) or 0)
    if others + hours > cap:
        left = max(cap - others, Decimal(0))
        kind = "planned" if column is ProdLog.planned_hours else "logged"
        message = f"Max {cap:g} h per day: {others:g} h already {kind}, {left:g} h left"
        raise AppError(422, "daily_hours_exceeded", message, fields={column.key: message})


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
    def day_sum(column: InstrumentedAttribute[Decimal | None]) -> Any:
        return func.coalesce(func.sum(column).over(partition_by=ProdLog.log_date), 0)

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.execute(
        stmt.add_columns(day_sum(ProdLog.hours_spent), day_sum(ProdLog.planned_hours))
        .order_by(ProdLog.log_date.desc(), ProdLog.created_at.desc(), ProdLog.id.desc())
        .limit(params.limit)
        .offset(params.offset)
    )
    items = [
        ProdLogListItem.model_validate(
            {
                **_fields(row, viewer),
                "day_total_hours": row[_ROW_LEN],
                "day_planned_hours": row[_ROW_LEN + 1],
            }
        )
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
    if params.activity_id is not None:
        stmt = stmt.where(ProdLog.activity_id == params.activity_id)
    return stmt


async def list_logs(db: AsyncSession, user: User, params: ProdLogQuery) -> Page[ProdLogListItem]:
    """The caller's own logs (for admins too: other people's logs are under /teams)."""
    stmt = _filter(_base_query().where(ProdLog.user_id == user.id), params)
    if params.task_id is not None:
        stmt = stmt.where(ProdLog.task_id == params.task_id)
    return await _page(db, stmt, params, user)


async def check_team_access(db: AsyncSession, user: User, team_id: int) -> None:
    """Admins: any existing team. Managers: their own team only (404 for others).
    Devs: no team access at all."""
    if user.role == Role.DEV:
        raise AppError(403, "forbidden", "Only managers and admins can view team data")
    if user.role == Role.MANAGER and user.team_id != team_id:
        raise AppError(404, "not_found", "Team not found")
    if await db.get(Team, team_id) is None:
        raise AppError(404, "not_found", "Team not found")


async def list_team_logs(
    db: AsyncSession, user: User, team_id: int, params: TeamLogQuery
) -> Page[ProdLogListItem]:
    """Logs whose team snapshot is `team_id`, whatever team the author is in now."""
    await check_team_access(db, user, team_id)
    stmt = _filter(_base_query().where(ProdLog.team_id == team_id), params)
    if params.user_id is not None:
        stmt = stmt.where(ProdLog.user_id == params.user_id)
    return await _page(db, stmt, params, user)


async def list_team_members(
    db: AsyncSession, user: User, team_id: int, params: PaginationParams
) -> Page[TeamMemberOut]:
    """Current members plus former members who have logs under this team."""
    await check_team_access(db, user, team_id)
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


async def create_log(
    db: AsyncSession, user: User, data: ProdLogCreate, settings: Settings
) -> ProdLogOut:
    sent = data.model_fields_set
    is_admin = user.role == Role.ADMIN
    week = plan_week(data.log_date, settings)
    if data.planned_hours is not None and not week.is_open and not is_admin:
        raise _week_locked(week, "planned_hours", "log the actual hours as unplanned work")
    project_id, category_id = data.project_id, data.category_id
    if data.task_id is not None:
        task = await _check_task(db, data.task_id, user.id)
        if "project_id" not in sent:
            project_id = await _active_or_none(db, "project_id", task.project_id)
        if category_id is None:
            category_id = await _active_or_none(db, "category_id", task.category_id)
    if category_id is None:
        raise invalid_reference("category_id", "Choose a category")
    if project_id is None:
        raise invalid_reference("project_id", "Choose a project")
    work_setup_id = data.work_setup_id or await _default_work_setup(db)
    refs = {
        "category_id": category_id,
        "project_id": project_id,
        "activity_id": data.activity_id,
        "work_setup_id": work_setup_id,
        "om_project_id": data.om_project_id,
        "deviation_reason_id": data.deviation_reason_id,
    }
    for field, value in refs.items():
        if value is not None:
            await check_ref(db, field, value, keep=None)
    await _check_links(db, _Links(category_id, project_id, data.activity_id, data.om_project_id))
    if data.planned_hours is None and data.hours_spent is None:
        raise _hours_required()

    log = ProdLog(
        user_id=user.id,
        team_id=user.team_id,
        task_id=data.task_id,
        log_date=data.log_date,
        work_setup_id=work_setup_id,
        activity_id=data.activity_id,
        project_id=project_id,
        category_id=category_id,
        om_project_id=data.om_project_id,
        is_planned=data.is_planned,
        planned_hours=data.planned_hours,
        hours_spent=data.hours_spent,
        title=data.title or None,
        description=data.description or None,
        deviation_reason_id=data.deviation_reason_id,
        updated_by=user.id,
    )
    cap = settings.workday_hours
    await _check_daily_total(db, log, ProdLog.hours_spent, data.hours_spent, None, cap)
    await _check_daily_total(db, log, ProdLog.planned_hours, data.planned_hours, None, cap)
    db.add(log)
    await db.commit()
    logger.info("prod_log_created", extra={"fields": {"log_id": log.id}})
    return await _load(db, user, log.id)


_REF_FIELDS = (
    "work_setup_id",
    "category_id",
    "project_id",
    "activity_id",
    "om_project_id",
    "deviation_reason_id",
)
_TEXT_FIELDS = ("title", "description")


def _check_planned_lock(log: ProdLog, data: ProdLogUpdate, settings: Settings) -> None:
    """Planned hours on a date in a locked week stay as they are: they cannot be set,
    changed or cleared there, nor moved to or from such a date."""
    sent = data.model_fields_set
    new_date = data.log_date if "log_date" in sent and data.log_date else log.log_date
    new_planned = data.planned_hours if "planned_hours" in sent else log.planned_hours
    if new_planned == log.planned_hours and new_date == log.log_date:
        return
    # Existing planned hours leave (or change on) their date; new ones arrive on theirs.
    for day, planned in ((log.log_date, log.planned_hours), (new_date, new_planned)):
        week = plan_week(day, settings)
        if planned is not None and not week.is_open:
            raise _week_locked(week, "planned_hours", "planned hours can no longer change")


async def update_log(
    db: AsyncSession, user: User, log_id: int, data: ProdLogUpdate, settings: Settings
) -> ProdLogOut:
    log = await _get_writable(db, user, log_id)
    sent = data.model_fields_set
    if user.role != Role.ADMIN:
        _check_planned_lock(log, data, settings)

    # Validate the final values before touching the row, so a rejected update leaves
    # nothing half-applied in the session.
    def final(field: str) -> Any:
        return getattr(data, field) if field in sent else getattr(log, field)

    for field in _REF_FIELDS:
        value = getattr(data, field)
        if field in sent and value is not None:
            await check_ref(db, field, value, keep=getattr(log, field))
    if "task_id" in sent and data.task_id is not None and data.task_id != log.task_id:
        await _check_task(db, data.task_id, log.user_id)
    new_links = _Links(
        final("category_id"), final("project_id"), final("activity_id"), final("om_project_id")
    )
    await _check_links(db, new_links, _links_of(log))
    if final("planned_hours") is None and final("hours_spent") is None:
        raise _hours_required()

    for field in (
        "log_date",
        "planned_hours",
        "hours_spent",
        "task_id",
        "is_planned",
        *_REF_FIELDS,
    ):
        if field in sent:
            setattr(log, field, getattr(data, field))
    for field in _TEXT_FIELDS:
        if field in sent:
            setattr(log, field, getattr(data, field) or None)

    cap = settings.workday_hours
    if sent & {"log_date", "hours_spent"}:
        await _check_daily_total(db, log, ProdLog.hours_spent, log.hours_spent, log.id, cap)
    if sent & {"log_date", "planned_hours"}:
        await _check_daily_total(db, log, ProdLog.planned_hours, log.planned_hours, log.id, cap)
    log.updated_by = user.id

    await db.commit()
    logger.info("prod_log_updated", extra={"fields": {"log_id": log.id}})
    return await _load(db, user, log.id)


async def delete_log(db: AsyncSession, user: User, log_id: int, settings: Settings) -> None:
    log = await _get_writable(db, user, log_id)
    # Rows holding planned hours are the week's plan: kept once the week is locked.
    if log.planned_hours is not None and user.role != Role.ADMIN:
        week = plan_week(log.log_date, settings)
        if not week.is_open:
            raise _week_locked(week, None, "rows with planned hours can no longer be deleted")
    await db.delete(log)
    await db.commit()
    logger.info("prod_log_deleted", extra={"fields": {"log_id": log_id}})


# ---------------------------------------------------------------- copy a plan


async def _copyable(db: AsyncSession, log: ProdLog) -> bool:
    """Every value on the row is active and the links still hold."""
    if log.project_id is None:
        return False
    refs = {
        "category_id": log.category_id,
        "project_id": log.project_id,
        "activity_id": log.activity_id,
        "work_setup_id": log.work_setup_id,
        "om_project_id": log.om_project_id,
    }
    try:
        for field, value in refs.items():
            if value is not None:
                await check_ref(db, field, value, keep=None)
        await _check_links(db, _links_of(log))
    except AppError:
        return False
    return True


async def copy_logs(db: AsyncSession, user: User, data: CopyLogs, settings: Settings) -> CopyResult:
    """Copy the caller's rows from a day or a week to days in open weeks, as planned rows.

    A target day whose planned total would pass WORKDAY_HOURS is skipped as a whole. Rows
    with an inactive or unlinked value are left out. All in one transaction.
    """
    for target in data.to_dates:
        week = plan_week(target, settings)
        if not week.is_open:
            raise _week_locked(week, "to_dates", "copy into a week that is still open")

    source_day = data.from_date or data.from_week or date.min  # the schema requires one
    if data.from_date is not None:
        start = end = source_day
    else:
        start = monday_of(source_day)
        end = start + timedelta(days=6)
    sources = (
        await db.scalars(
            select(ProdLog)
            .where(ProdLog.user_id == user.id, ProdLog.log_date.between(start, end))
            .order_by(ProdLog.log_date, ProdLog.created_at, ProdLog.id)
        )
    ).all()
    if not sources:
        message = "There are no rows to copy on the chosen day or week"
        raise AppError(422, "nothing_to_copy", message)

    usable = [log for log in sources if await _copyable(db, log)]
    by_weekday: dict[int, list[ProdLog]] = defaultdict(list)
    for log in usable:
        by_weekday[log.log_date.weekday()].append(log)

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"prod_logs:user:{user.id}"},
    )
    planned_on = dict(
        (
            await db.execute(
                select(ProdLog.log_date, func.coalesce(func.sum(ProdLog.planned_hours), 0))
                .where(ProdLog.user_id == user.id, ProdLog.log_date.in_(data.to_dates))
                .group_by(ProdLog.log_date)
            )
        ).all()
    )

    days: list[CopyDayResult] = []
    for target in sorted(data.to_dates):
        rows = usable if data.from_date is not None else by_weekday.get(target.weekday(), [])
        hours = [log.planned_hours or log.hours_spent or Decimal(0) for log in rows]
        if not rows:
            days.append(CopyDayResult(date=target, created=0, skipped_reason="nothing_to_copy"))
            continue
        if Decimal(planned_on.get(target, 0)) + sum(hours, Decimal(0)) > settings.workday_hours:
            days.append(
                CopyDayResult(date=target, created=0, skipped_reason="daily_hours_exceeded")
            )
            continue
        for log, planned in zip(rows, hours, strict=True):
            db.add(_copy_of(log, user, target, planned))
        days.append(CopyDayResult(date=target, created=len(rows), skipped_reason=None))

    await db.commit()
    created = sum(day.created for day in days)
    logger.info("prod_logs_copied", extra={"fields": {"created": created}})
    return CopyResult(created=created, days=days, skipped_rows=len(sources) - len(usable))


def _copy_of(log: ProdLog, user: User, target: date, planned: Decimal) -> ProdLog:
    return ProdLog(
        user_id=user.id,
        team_id=user.team_id,
        task_id=log.task_id,
        log_date=target,
        work_setup_id=log.work_setup_id,
        activity_id=log.activity_id,
        project_id=log.project_id,
        category_id=log.category_id,
        om_project_id=log.om_project_id,
        is_planned=True,
        planned_hours=planned,
        hours_spent=None,
        title=log.title,
        updated_by=user.id,
    )
