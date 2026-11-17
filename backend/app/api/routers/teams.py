"""Team views: managers see their own team, admins any team. Devs get 403."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser
from app.core.pagination import Page, Pagination
from app.db.session import SessionDep
from app.schemas.prod_logs import ProdLogListItem, TeamLogQuery, TeamMemberOut
from app.services import prod_logs as service

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/{team_id}/logs", response_model=Page[ProdLogListItem])
async def list_team_logs(
    team_id: int,
    params: Annotated[TeamLogQuery, Query()],
    user: CurrentUser,
    db: SessionDep,
) -> Page[ProdLogListItem]:
    """Read-only. Filters on the team snapshot stored on each log, so logs stay with
    the team they were written in when the author changes teams."""
    return await service.list_team_logs(db, user, team_id, params)


@router.get("/{team_id}/members", response_model=Page[TeamMemberOut])
async def list_team_members(
    team_id: int, params: Pagination, user: CurrentUser, db: SessionDep
) -> Page[TeamMemberOut]:
    """Current members plus former members with logs under this team (for filters)."""
    return await service.list_team_members(db, user, team_id, params)
