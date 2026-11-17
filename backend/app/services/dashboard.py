"""Dashboard aggregations, computed in SQL.

Every aggregation over prod logs takes a `scope`: the WHERE clause that decides whose
logs are counted. The personal dashboard passes the caller's own logs only
(`own_logs`); team dashboards will pass a `prod_logs.team_id` filter instead.

Weeks start on Monday. "Today" and task completion dates follow APP_TIMEZONE;
`log_date` is already a calendar date.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Date, DateTime, cast, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models import Category, ProdLog, Project, Status, Task, User
from app.schemas.dashboard import (
    WEEKS_IN_TREND,
    CategoryHours,
    DateRangeQuery,
    DayHours,
    HoursByCategory,
    HoursByProject,
    HoursPerDay,
    HoursPerWeek,
    ProjectHours,
    TaskCounts,
    WeekHours,
)
from app.schemas.tasks import LookupRef, ProjectRef

ZERO = Decimal("0.00")

LogScope = ColumnElement[bool]


def own_logs(user: User) -> LogScope:
    return ProdLog.user_id == user.id


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _hours_sum() -> ColumnElement[Decimal]:
    return func.coalesce(func.sum(ProdLog.hours_spent), ZERO)


def _in_range(rng: DateRangeQuery) -> ColumnElement[bool]:
    return ProdLog.log_date.between(rng.date_from, rng.date_to)


# ---------------------------------------------------------------- hours over time


async def hours_per_day(db: AsyncSession, scope: LogScope, any_day: date) -> HoursPerDay:
    """Hours for each day of the week containing `any_day`."""
    start = monday_of(any_day)
    end = start + timedelta(days=6)
    rows = await db.execute(
        select(ProdLog.log_date, _hours_sum())
        .where(scope, ProdLog.log_date.between(start, end))
        .group_by(ProdLog.log_date)
    )
    by_day: dict[date, Decimal] = dict(rows.all())
    days = [
        DayHours(date=day, hours=by_day.get(day, ZERO))
        for day in (start + timedelta(days=i) for i in range(7))
    ]
    return HoursPerDay(week_start=start, week_end=end, days=days, total=sum(by_day.values(), ZERO))


async def hours_per_week(
    db: AsyncSession, scope: LogScope, today: date, weeks: int = WEEKS_IN_TREND
) -> HoursPerWeek:
    """Hours per week for the last `weeks` weeks, ending with the week of `today`."""
    last = monday_of(today)
    first = last - timedelta(weeks=weeks - 1)
    # Cast to a plain timestamp first so date_trunc never involves the session time zone.
    week_start = cast(func.date_trunc("week", cast(ProdLog.log_date, DateTime())), Date)
    rows = await db.execute(
        select(week_start, _hours_sum())
        .where(scope, ProdLog.log_date.between(first, last + timedelta(days=6)))
        .group_by(week_start)
    )
    by_week: dict[date, Decimal] = dict(rows.all())
    return HoursPerWeek(
        weeks=[
            WeekHours(week_start=week, hours=by_week.get(week, ZERO))
            for week in (first + timedelta(weeks=i) for i in range(weeks))
        ]
    )


# ---------------------------------------------------------------- hours by dimension


async def hours_by_project(
    db: AsyncSession, scope: LogScope, rng: DateRangeQuery
) -> HoursByProject:
    hours = _hours_sum().label("hours")
    rows = await db.execute(
        select(Project, hours)
        .select_from(ProdLog)
        .outerjoin(Project, Project.id == ProdLog.project_id)
        .where(scope, _in_range(rng))
        .group_by(Project.id)
        .order_by(hours.desc(), Project.name.nulls_last())
    )
    items = [
        ProjectHours(
            project=ProjectRef.model_validate(project) if project is not None else None,
            hours=total,
        )
        for project, total in rows.all()
    ]
    return HoursByProject(
        date_from=rng.date_from,
        date_to=rng.date_to,
        items=items,
        total=sum((item.hours for item in items), ZERO),
    )


async def hours_by_category(
    db: AsyncSession, scope: LogScope, rng: DateRangeQuery
) -> HoursByCategory:
    hours = _hours_sum().label("hours")
    rows = await db.execute(
        select(Category, hours)
        .join(ProdLog, ProdLog.category_id == Category.id)
        .where(scope, _in_range(rng))
        .group_by(Category.id)
        .order_by(hours.desc(), Category.sort_order, Category.label)
    )
    items = [
        CategoryHours(category=LookupRef.model_validate(category), hours=total)
        for category, total in rows.all()
    ]
    return HoursByCategory(
        date_from=rng.date_from,
        date_to=rng.date_to,
        items=items,
        total=sum((item.hours for item in items), ZERO),
    )


# ---------------------------------------------------------------- tasks


async def task_counts(
    db: AsyncSession, user: User, rng: DateRangeQuery, today: date, tz_name: str
) -> TaskCounts:
    """The caller's own tasks: completed within the range, open now, overdue now."""
    completed_on = cast(func.timezone(tz_name, Task.completed_at), Date)
    open_ = not_(Status.is_done)
    row = (
        await db.execute(
            select(
                func.count().filter(
                    Status.is_done, completed_on.between(rng.date_from, rng.date_to)
                ),
                func.count().filter(open_),
                func.count().filter(open_, Task.due_date < today),
            )
            .select_from(Task)
            .join(Status, Status.id == Task.status_id)
            .where(Task.user_id == user.id)
        )
    ).one()
    completed, open_count, overdue = row
    return TaskCounts(
        date_from=rng.date_from,
        date_to=rng.date_to,
        completed=completed,
        open=open_count,
        overdue=overdue,
    )


# ---------------------------------------------------------------- personal dashboard


async def personal_hours_per_day(db: AsyncSession, user: User, any_day: date) -> HoursPerDay:
    return await hours_per_day(db, own_logs(user), any_day)


async def personal_hours_per_week(db: AsyncSession, user: User, today: date) -> HoursPerWeek:
    return await hours_per_week(db, own_logs(user), today)


async def personal_hours_by_project(
    db: AsyncSession, user: User, rng: DateRangeQuery
) -> HoursByProject:
    return await hours_by_project(db, own_logs(user), rng)


async def personal_hours_by_category(
    db: AsyncSession, user: User, rng: DateRangeQuery
) -> HoursByCategory:
    return await hours_by_category(db, own_logs(user), rng)
