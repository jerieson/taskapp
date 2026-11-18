"""Weekly planning status: your own, and a team's (managers: own team; admins: any
team; devs get 403)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser
from app.db.session import SessionDep
from app.schemas.planning import PlanningStatus, PlanWeekQuery, TeamPlanningStatus
from app.services import planning as service

router = APIRouter(tags=["planning"])

WeekParams = Annotated[PlanWeekQuery, Query()]


@router.get("/planning/status", response_model=PlanningStatus)
async def own_status(
    params: WeekParams, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> PlanningStatus:
    """Your planned hours per day for a week, its deadline, and whether to show the
    planning reminder."""
    return await service.own_status(db, user, params.week, settings)


@router.get("/teams/{team_id}/planning/status", response_model=TeamPlanningStatus)
async def team_status(
    team_id: int, params: WeekParams, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> TeamPlanningStatus:
    """Each member's planned hours per day for a week and whether they have planned."""
    return await service.team_status(db, user, team_id, params.week, settings)
