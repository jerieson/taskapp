"""Projects. Admin writes; every role reads active projects. Never deleted.

A project is linked to the categories it can be logged under and to the activity group
whose activities it offers. Newly linked categories and groups must be active; inactive
ones already on the project may stay.
"""

import logging

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.pagination import Page, PaginationParams
from app.models import ActivityGroup, Category, Project
from app.schemas.lookups import ProjectCreate, ProjectOut, ProjectUpdate

logger = logging.getLogger("app.projects")


def _name_taken() -> AppError:
    message = "A project with this name already exists"
    return AppError(409, "project_name_taken", message, fields={"name": message})


async def _get(db: AsyncSession, project_id: int) -> Project:
    project = await db.get(Project, project_id, populate_existing=True)
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


def _invalid(field: str, message: str) -> AppError:
    return AppError(422, "invalid_reference", message, fields={field: message})


async def _categories(db: AsyncSession, ids: list[int], keep: list[Category]) -> list[Category]:
    if len(ids) != len(set(ids)):
        raise _invalid("category_ids", "List each category once")
    kept = {category.id for category in keep}
    found = {c.id: c for c in await db.scalars(select(Category).where(Category.id.in_(ids)))}
    for category_id in ids:
        category = found.get(category_id)
        if category is None or (not category.is_active and category_id not in kept):
            raise _invalid("category_ids", "Choose active categories")
    return [found[category_id] for category_id in ids]


async def _check_group(db: AsyncSession, group_id: int, keep: int | None) -> None:
    group = await db.get(ActivityGroup, group_id)
    if group is None or (not group.is_active and group_id != keep):
        raise _invalid("activity_group_id", "Choose an active activity group")


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
    if data.activity_group_id is not None:
        await _check_group(db, data.activity_group_id, keep=None)
    project = Project(
        name=data.name,
        description=data.description,
        is_active=True,
        activity_group_id=data.activity_group_id,
        categories=await _categories(db, data.category_ids, keep=[]),
    )
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
    if data.category_ids is not None:
        project.categories = await _categories(db, data.category_ids, keep=project.categories)
    if "activity_group_id" in data.model_fields_set:
        if data.activity_group_id is not None:
            await _check_group(db, data.activity_group_id, keep=project.activity_group_id)
        project.activity_group_id = data.activity_group_id
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
