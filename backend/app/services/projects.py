"""Projects. Admin writes; every role reads active projects. Never deleted."""

import logging

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.pagination import Page, PaginationParams
from app.models import Project
from app.schemas.lookups import ProjectCreate, ProjectOut, ProjectUpdate

logger = logging.getLogger("app.projects")


def _name_taken() -> AppError:
    message = "A project with this name already exists"
    return AppError(409, "project_name_taken", message, fields={"name": message})


async def _get(db: AsyncSession, project_id: int) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise AppError(404, "not_found", "Project not found")
    return project


async def _ensure_name_free(db: AsyncSession, name: str, exclude_id: int | None = None) -> None:
    cond = func.lower(Project.name) == name.lower()
    if exclude_id is not None:
        cond = cond & (Project.id != exclude_id)
    if await db.scalar(select(exists().where(cond))):
        raise _name_taken()


async def _commit(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:  # lost a race on the unique name
        await db.rollback()
        raise _name_taken() from exc


async def list_projects(
    db: AsyncSession, params: PaginationParams, include_inactive: bool
) -> Page[ProjectOut]:
    stmt = select(Project)
    if not include_inactive:
        stmt = stmt.where(Project.is_active)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.scalars(
        stmt.order_by(func.lower(Project.name), Project.id)
        .limit(params.limit)
        .offset(params.offset)
    )
    return Page[ProjectOut].build(rows.all(), total, params)


async def create_project(db: AsyncSession, data: ProjectCreate) -> Project:
    await _ensure_name_free(db, data.name)
    project = Project(name=data.name, description=data.description, is_active=True)
    db.add(project)
    await _commit(db)
    await db.refresh(project)
    logger.info("project_created", extra={"fields": {"project_id": project.id}})
    return project


async def update_project(db: AsyncSession, project_id: int, data: ProjectUpdate) -> Project:
    project = await _get(db, project_id)
    if data.name is not None and data.name != project.name:
        await _ensure_name_free(db, data.name, exclude_id=project.id)
        project.name = data.name
    if data.description is not None:
        project.description = data.description
    await _commit(db)
    await db.refresh(project)
    logger.info("project_updated", extra={"fields": {"project_id": project.id}})
    return project


async def set_active(db: AsyncSession, project_id: int, active: bool) -> Project:
    project = await _get(db, project_id)
    project.is_active = active
    await db.commit()
    await db.refresh(project)
    logger.info(
        "project_activated" if active else "project_deactivated",
        extra={"fields": {"project_id": project.id}},
    )
    return project
