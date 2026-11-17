"""Projects. Every role lists active projects; only admins write. No delete endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentUser, require_role
from app.core.pagination import Page
from app.db.session import SessionDep
from app.models import Project, Role
from app.schemas.lookups import LookupQuery, ProjectCreate, ProjectOut, ProjectUpdate
from app.services import lookups as lookup_service
from app.services import projects as service

router = APIRouter(prefix="/projects", tags=["projects"])
AdminOnly = [Depends(require_role(Role.ADMIN))]


@router.get("", response_model=Page[ProjectOut])
async def list_projects(
    params: Annotated[LookupQuery, Query()], user: CurrentUser, db: SessionDep
) -> Page[ProjectOut]:
    lookup_service.ensure_can_include_inactive(user, params.include_inactive)
    return await service.list_projects(db, params, params.include_inactive)


@router.post("", response_model=ProjectOut, status_code=201, dependencies=AdminOnly)
async def create_project(data: ProjectCreate, db: SessionDep) -> Project:
    return await service.create_project(db, data)


@router.patch("/{project_id}", response_model=ProjectOut, dependencies=AdminOnly)
async def update_project(project_id: int, data: ProjectUpdate, db: SessionDep) -> Project:
    return await service.update_project(db, project_id, data)


@router.post("/{project_id}/activate", response_model=ProjectOut, dependencies=AdminOnly)
async def activate_project(project_id: int, db: SessionDep) -> Project:
    return await service.set_active(db, project_id, True)


@router.post("/{project_id}/deactivate", response_model=ProjectOut, dependencies=AdminOnly)
async def deactivate_project(project_id: int, db: SessionDep) -> Project:
    return await service.set_active(db, project_id, False)
