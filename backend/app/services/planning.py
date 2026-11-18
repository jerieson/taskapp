"""Weekly planning status: who has planned which week, and how many hours per day.

The caller's own status is open to everyone. A team's status follows team access:
managers their own team, admins any team, devs never (`prod_logs.check_team_access`).
Team hours come from the team snapshot on each row, like the team dashboards.
"""

from collections import defaultdict
from datetime import UTC, date
from decimal import Decimal

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.weeks import PlanWeek, next_week, plan_week
from app.models import ProdLog, User
from app.schemas.planning import (
    MemberPlan,
    PlanDay,
    PlanningStatus,
    PlanWeekOut,
    TeamPlanningStatus,
)
from app.services.dashboard import team_members
from app.services.prod_logs import check_team_access

ZERO = Decimal(0)


def _week(day: date | None, settings: Settings) -> PlanWeek:
    return plan_week(day, settings) if day is not None else next_week(settings)


def _week_out(week: PlanWeek, settings: Settings) -> dict[str, object]:
    return PlanWeekOut(
        week_start=week.start,
        week_end=week.end,
        deadline=week.deadline.astimezone(UTC),
        is_open=week.is_open,
        workday_hours=settings.workday_hours,
    ).model_dump()


async def _planned_by_user(
    db: AsyncSession, scope: ColumnElement[bool], week: PlanWeek
) -> dict[int, dict[date, Decimal]]:
    """{user_id: {date: planned hours}} for rows with planned hours, Monday to Friday."""
    rows = await db.execute(
        select(ProdLog.user_id, ProdLog.log_date, func.sum(ProdLog.planned_hours))
        .where(
            scope,
            ProdLog.planned_hours.is_not(None),
            ProdLog.log_date.between(week.start, week.end),
        )
        .group_by(ProdLog.user_id, ProdLog.log_date)
    )
    out: dict[int, dict[date, Decimal]] = defaultdict(dict)
    for user_id, day, hours in rows.all():
        out[user_id][day] = hours
    return out


def _days(week: PlanWeek, hours: dict[date, Decimal]) -> list[PlanDay]:
    return [PlanDay(date=d, planned_hours=hours.get(d, ZERO)) for d in week.days]


async def own_status(
    db: AsyncSession, user: User, day: date | None, settings: Settings
) -> PlanningStatus:
    week = _week(day, settings)
    hours = (await _planned_by_user(db, ProdLog.user_id == user.id, week)).get(user.id, {})
    has_planned = bool(hours)
    return PlanningStatus(
        **_week_out(week, settings),
        days=_days(week, hours),
        total=sum(hours.values(), ZERO),
        has_planned=has_planned,
        show_reminder=not has_planned and week.in_reminder_window,
    )


async def team_status(
    db: AsyncSession, user: User, team_id: int, day: date | None, settings: Settings
) -> TeamPlanningStatus:
    await check_team_access(db, user, team_id)
    week = _week(day, settings)
    by_user = await _planned_by_user(db, ProdLog.team_id == team_id, week)
    members = await team_members(db, team_id, by_user)
    return TeamPlanningStatus(
        **_week_out(week, settings),
        members=[
            MemberPlan(
                member=member,
                days=_days(week, by_user.get(member.id, {})),
                total=sum(by_user.get(member.id, {}).values(), ZERO),
                has_planned=member.id in by_user,
            )
            for member in members
        ],
    )
