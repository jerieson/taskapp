from fastapi import APIRouter, Depends

from app.core.dependencies import require_role
from app.core.pagination import Page, Pagination
from app.db.session import SessionDep
from app.models import Role
from app.schemas.teams import TeamIn, TeamOut
from app.services import teams as team_service

router = APIRouter(
    prefix="/admin/teams", tags=["admin"], dependencies=[Depends(require_role(Role.ADMIN))]
)


@router.get("", response_model=Page[TeamOut])
async def list_teams(params: Pagination, db: SessionDep) -> Page[TeamOut]:
    return await team_service.list_teams(db, params)


@router.post("", response_model=TeamOut, status_code=201)
async def create_team(data: TeamIn, db: SessionDep) -> TeamOut:
    return await team_service.create_team(db, data)


@router.patch("/{team_id}", response_model=TeamOut)
async def rename_team(team_id: int, data: TeamIn, db: SessionDep) -> TeamOut:
    return await team_service.rename_team(db, team_id, data)


@router.delete("/{team_id}", status_code=204)
async def delete_team(team_id: int, db: SessionDep) -> None:
    """Blocked (409) while any user or prod log references the team."""
    await team_service.delete_team(db, team_id)
