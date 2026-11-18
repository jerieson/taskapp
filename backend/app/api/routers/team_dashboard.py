"""Team dashboard: managers see their own team, admins any team, devs get 403.

Hours come from the team snapshot on each prod log, so they stay with the team they
were logged in when the author changes teams. Task data is counts only."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser
from app.db.session import SessionDep
from app.schemas.dashboard import (
    DateRangeQuery,
    HoursByActivity,
    HoursByCategory,
    HoursByMember,
    HoursByProject,
    TeamHoursPerDay,
    TeamHoursPerWeek,
    TeamTaskCounts,
    WeekQuery,
)
from app.services import dashboard as service

router = APIRouter(prefix="/teams/{team_id}/dashboard", tags=["teams"])

RangeParams = Annotated[DateRangeQuery, Query()]


def _today(settings: SettingsDep) -> date:
    return datetime.now(settings.tz).date()


@router.get("/hours/daily", response_model=TeamHoursPerDay)
async def hours_per_day(
    team_id: int,
    params: Annotated[WeekQuery, Query()],
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
) -> TeamHoursPerDay:
    """Team hours on each day of one week (Monday to Sunday), in total and per member."""
    return await service.team_hours_per_day(db, user, team_id, params.week or _today(settings))


@router.get("/hours/weekly", response_model=TeamHoursPerWeek)
async def hours_per_week(
    team_id: int, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> TeamHoursPerWeek:
    """Team hours per week for the last 8 weeks, in total and per member."""
    return await service.team_hours_per_week(db, user, team_id, _today(settings))


@router.get("/hours/by-member", response_model=HoursByMember)
async def hours_by_member(
    team_id: int, params: RangeParams, user: CurrentUser, db: SessionDep
) -> HoursByMember:
    return await service.team_hours_by_member(db, user, team_id, params)


@router.get("/hours/by-project", response_model=HoursByProject)
async def hours_by_project(
    team_id: int, params: RangeParams, user: CurrentUser, db: SessionDep
) -> HoursByProject:
    return await service.team_hours_by_project(db, user, team_id, params)


@router.get("/hours/by-category", response_model=HoursByCategory)
async def hours_by_category(
    team_id: int, params: RangeParams, user: CurrentUser, db: SessionDep
) -> HoursByCategory:
    return await service.team_hours_by_category(db, user, team_id, params)


@router.get("/hours/by-activity", response_model=HoursByActivity)
async def hours_by_activity(
    team_id: int, params: RangeParams, user: CurrentUser, db: SessionDep
) -> HoursByActivity:
    return await service.team_hours_by_activity(db, user, team_id, params)


@router.get("/tasks", response_model=TeamTaskCounts)
async def task_counts(
    team_id: int, params: RangeParams, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> TeamTaskCounts:
    """Task counts per current team member: completed within the range, open and overdue
    now. Counts only; no task contents."""
    return await service.team_task_counts(
        db, user, team_id, params, _today(settings), settings.app_timezone
    )
