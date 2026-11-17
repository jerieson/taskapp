"""Dashboard aggregations, computed in SQL.

Every aggregation over prod logs takes a `scope`: the WHERE clause that decides whose
logs are counted. The personal dashboard passes the caller's own logs only
(`own_logs`); team dashboards pass the team snapshot (`team_logs`) instead.

Weeks start on Monday. "Today" and task completion dates follow APP_TIMEZONE;
`log_date` is already a calendar date.
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, and_, cast, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models import Category, ProdLog, Project, Status, Task, User
from app.schemas.dashboard import (
    WEEKS_IN_TREND,
    CategoryHours,
    DateRangeQuery,
    DayHours,
    HoursByCategory,
    HoursByMember,
    HoursByProject,
    HoursPerDay,
    HoursPerWeek,
    MemberDays,
    MemberHours,
    MemberTaskCounts,
    MemberWeeks,
    ProjectHours,
    TaskCounts,
    TeamHoursPerDay,
    TeamHoursPerWeek,
    TeamTaskCounts,
    WeekHours,
)
from app.schemas.prod_logs import TeamMemberOut
from app.schemas.tasks import LookupRef, ProjectRef
from app.services.prod_logs import check_team_access

ZERO = Decimal("0.00")

LogScope = ColumnElement[bool]


def own_logs(user: User) -> LogScope:
    return ProdLog.user_id == user.id


def team_logs(team_id: int) -> LogScope:
    return ProdLog.team_id == team_id


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _hours_sum() -> ColumnElement[Decimal]:
    return func.coalesce(func.sum(ProdLog.hours_spent), ZERO)


def _in_range(rng: DateRangeQuery) -> ColumnElement[bool]:
    return ProdLog.log_date.between(rng.date_from, rng.date_to)


# ---------------------------------------------------------------- hours over time


def _week_days(any_day: date) -> list[date]:
    start = monday_of(any_day)
    return [start + timedelta(days=i) for i in range(7)]


def _trend_weeks(today: date, weeks: int = WEEKS_IN_TREND) -> list[date]:
    last = monday_of(today)
    return [last - timedelta(weeks=weeks - 1 - i) for i in range(weeks)]


def _week_start(column: Any) -> ColumnElement[date]:
    # Cast to a plain timestamp first so date_trunc never involves the session time zone.
    return cast(func.date_trunc("week", cast(column, DateTime())), Date)


async def hours_per_day(db: AsyncSession, scope: LogScope, any_day: date) -> HoursPerDay:
    """Hours for each day of the week containing `any_day`."""
    days = _week_days(any_day)
    rows = await db.execute(
        select(ProdLog.log_date, _hours_sum())
        .where(scope, ProdLog.log_date.between(days[0], days[-1]))
        .group_by(ProdLog.log_date)
    )
    by_day: dict[date, Decimal] = dict(rows.all())
    return HoursPerDay(
        week_start=days[0],
        week_end=days[-1],
        days=[DayHours(date=day, hours=by_day.get(day, ZERO)) for day in days],
        total=sum(by_day.values(), ZERO),
    )


async def hours_per_week(
    db: AsyncSession, scope: LogScope, today: date, weeks: int = WEEKS_IN_TREND
) -> HoursPerWeek:
    """Hours per week for the last `weeks` weeks, ending with the week of `today`."""
    all_weeks = _trend_weeks(today, weeks)
    week_start = _week_start(ProdLog.log_date)
    rows = await db.execute(
        select(week_start, _hours_sum())
        .where(scope, ProdLog.log_date.between(all_weeks[0], all_weeks[-1] + timedelta(days=6)))
        .group_by(week_start)
    )
    by_week: dict[date, Decimal] = dict(rows.all())
    return HoursPerWeek(
        weeks=[WeekHours(week_start=week, hours=by_week.get(week, ZERO)) for week in all_weeks]
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


def _task_count_columns(rng: DateRangeQuery, today: date, tz_name: str) -> list[Any]:
    """completed (within the range, still done), open now, overdue now."""
    completed_on = cast(func.timezone(tz_name, Task.completed_at), Date)
    open_ = not_(Status.is_done)
    return [
        func.count().filter(Status.is_done, completed_on.between(rng.date_from, rng.date_to)),
        func.count().filter(open_),
        func.count().filter(open_, Task.due_date < today),
    ]


async def task_counts(
    db: AsyncSession, user: User, rng: DateRangeQuery, today: date, tz_name: str
) -> TaskCounts:
    """The caller's own tasks: completed within the range, open now, overdue now."""
    row = (
        await db.execute(
            select(*_task_count_columns(rng, today, tz_name))
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


# ---------------------------------------------------------------- team dashboard
#
# Every entry point checks team access first: managers their own team, admins any
# team, devs never (`prod_logs.check_team_access`). Hours follow the
# team snapshot on each log; task counts cover the team's current active members.


def _member_out(user: User, team_id: int) -> TeamMemberOut:
    return TeamMemberOut(
        id=user.id,
        username=user.username,
        is_active=user.is_active,
        is_current_member=user.team_id == team_id,
    )


async def _members(
    db: AsyncSession, team_id: int, with_hours: Iterable[int]
) -> list[TeamMemberOut]:
    """Active current members, plus anyone with hours in the period, by username."""
    users = await db.scalars(
        select(User)
        .where(or_(and_(User.team_id == team_id, User.is_active), User.id.in_(list(with_hours))))
        .order_by(func.lower(User.username), User.id)
    )
    return [_member_out(u, team_id) for u in users.all()]


async def _hours_by_user(
    db: AsyncSession, scope: LogScope, bucket: Any, start: date, end: date
) -> dict[int, dict[date, Decimal]]:
    """{user_id: {bucket: hours}} for logs dated start..end."""
    rows = await db.execute(
        select(ProdLog.user_id, bucket, _hours_sum())
        .where(scope, ProdLog.log_date.between(start, end))
        .group_by(ProdLog.user_id, bucket)
    )
    out: dict[int, dict[date, Decimal]] = defaultdict(dict)
    for user_id, key, hours in rows.all():
        out[user_id][key] = hours
    return out


def _team_totals(by_user: dict[int, dict[date, Decimal]], keys: list[date]) -> dict[date, Decimal]:
    return {key: sum((hours.get(key, ZERO) for hours in by_user.values()), ZERO) for key in keys}


async def team_hours_per_day(
    db: AsyncSession, user: User, team_id: int, any_day: date
) -> TeamHoursPerDay:
    await check_team_access(db, user, team_id)
    days = _week_days(any_day)
    by_user = await _hours_by_user(db, team_logs(team_id), ProdLog.log_date, days[0], days[-1])
    team = _team_totals(by_user, days)
    members = [
        MemberDays(
            member=member,
            days=[DayHours(date=day, hours=by_user[member.id].get(day, ZERO)) for day in days],
            total=sum(by_user[member.id].values(), ZERO),
        )
        for member in await _members(db, team_id, by_user)
    ]
    return TeamHoursPerDay(
        week_start=days[0],
        week_end=days[-1],
        days=[DayHours(date=day, hours=team[day]) for day in days],
        total=sum(team.values(), ZERO),
        members=members,
    )


async def team_hours_per_week(
    db: AsyncSession, user: User, team_id: int, today: date
) -> TeamHoursPerWeek:
    await check_team_access(db, user, team_id)
    weeks = _trend_weeks(today)
    by_user = await _hours_by_user(
        db,
        team_logs(team_id),
        _week_start(ProdLog.log_date),
        weeks[0],
        weeks[-1] + timedelta(days=6),
    )
    team = _team_totals(by_user, weeks)
    members = [
        MemberWeeks(
            member=member,
            weeks=[
                WeekHours(week_start=week, hours=by_user[member.id].get(week, ZERO))
                for week in weeks
            ],
            total=sum(by_user[member.id].values(), ZERO),
        )
        for member in await _members(db, team_id, by_user)
    ]
    return TeamHoursPerWeek(
        weeks=[WeekHours(week_start=week, hours=team[week]) for week in weeks],
        members=members,
    )


async def team_hours_by_member(
    db: AsyncSession, user: User, team_id: int, rng: DateRangeQuery
) -> HoursByMember:
    await check_team_access(db, user, team_id)
    rows = await db.execute(
        select(ProdLog.user_id, _hours_sum())
        .where(team_logs(team_id), _in_range(rng))
        .group_by(ProdLog.user_id)
    )
    by_user: dict[int, Decimal] = dict(rows.all())
    members = await _members(db, team_id, by_user)
    items = sorted(
        (MemberHours(member=m, hours=by_user.get(m.id, ZERO)) for m in members),
        key=lambda item: -item.hours,  # stable: ties keep username order
    )
    return HoursByMember(
        date_from=rng.date_from,
        date_to=rng.date_to,
        items=items,
        total=sum(by_user.values(), ZERO),
    )


async def team_hours_by_project(
    db: AsyncSession, user: User, team_id: int, rng: DateRangeQuery
) -> HoursByProject:
    await check_team_access(db, user, team_id)
    return await hours_by_project(db, team_logs(team_id), rng)


async def team_hours_by_category(
    db: AsyncSession, user: User, team_id: int, rng: DateRangeQuery
) -> HoursByCategory:
    await check_team_access(db, user, team_id)
    return await hours_by_category(db, team_logs(team_id), rng)


async def team_task_counts(
    db: AsyncSession, user: User, team_id: int, rng: DateRangeQuery, today: date, tz_name: str
) -> TeamTaskCounts:
    """Counts per active current member. Never selects task titles or descriptions."""
    await check_team_access(db, user, team_id)
    members = await _members(db, team_id, ())
    rows = await db.execute(
        select(Task.user_id, *_task_count_columns(rng, today, tz_name))
        .select_from(Task)
        .join(Status, Status.id == Task.status_id)
        .where(Task.user_id.in_([m.id for m in members]))
        .group_by(Task.user_id)
    )
    counts = {user_id: (completed, open_, overdue) for user_id, completed, open_, overdue in rows}
    items = []
    for member in members:
        completed, open_count, overdue = counts.get(member.id, (0, 0, 0))
        items.append(
            MemberTaskCounts(member=member, completed=completed, open=open_count, overdue=overdue)
        )
    return TeamTaskCounts(date_from=rng.date_from, date_to=rng.date_to, items=items)
