"""The caller's personal dashboard. Every number comes from the caller's own data only
(admins included)."""

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
    HoursByProject,
    HoursPerWeek,
    PersonalHoursPerDay,
    TaskCounts,
    WeekQuery,
)
from app.services import dashboard as service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

RangeParams = Annotated[DateRangeQuery, Query()]


def _today(settings: SettingsDep) -> date:
    return datetime.now(settings.tz).date()


@router.get("/hours/daily", response_model=PersonalHoursPerDay)
async def hours_per_day(
    params: Annotated[WeekQuery, Query()],
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
) -> PersonalHoursPerDay:
    """Actual hours on each day of one week (Monday to Sunday), with planned hours."""
    return await service.personal_hours_per_day(db, user, params.week or _today(settings))


@router.get("/hours/weekly", response_model=HoursPerWeek)
async def hours_per_week(user: CurrentUser, db: SessionDep, settings: SettingsDep) -> HoursPerWeek:
    """Hours logged per week for the last 8 weeks, including the current one."""
    return await service.personal_hours_per_week(db, user, _today(settings))


@router.get("/hours/by-project", response_model=HoursByProject)
async def hours_by_project(
    params: RangeParams, user: CurrentUser, db: SessionDep
) -> HoursByProject:
    return await service.personal_hours_by_project(db, user, params)


@router.get("/hours/by-category", response_model=HoursByCategory)
async def hours_by_category(
    params: RangeParams, user: CurrentUser, db: SessionDep
) -> HoursByCategory:
    return await service.personal_hours_by_category(db, user, params)


@router.get("/hours/by-activity", response_model=HoursByActivity)
async def hours_by_activity(
    params: RangeParams, user: CurrentUser, db: SessionDep
) -> HoursByActivity:
    return await service.personal_hours_by_activity(db, user, params)


@router.get("/tasks", response_model=TaskCounts)
async def task_counts(
    params: RangeParams, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> TaskCounts:
    """Tasks completed within the range, plus tasks open and overdue right now."""
    return await service.task_counts(db, user, params, _today(settings), settings.app_timezone)
