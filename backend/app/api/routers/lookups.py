"""Categories, statuses and priorities.

Every role can list active values (for selects); only admins write or list inactive
values. There are no delete endpoints: values are deactivated instead.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentUser, require_role
from app.core.pagination import Page
from app.db.session import SessionDep
from app.models import Category, Priority, Role, Status
from app.schemas.lookups import (
    CategoryOut,
    LookupCreate,
    LookupQuery,
    LookupUpdate,
    PriorityOut,
    ReorderIn,
    StatusCreate,
    StatusOut,
    StatusUpdate,
)
from app.services import lookups as service

AdminOnly = [Depends(require_role(Role.ADMIN))]
Query_ = Annotated[LookupQuery, Query()]


# ---------------------------------------------------------------- categories

categories = APIRouter(prefix="/categories", tags=["dropdowns"])


@categories.get("", response_model=Page[CategoryOut])
async def list_categories(params: Query_, user: CurrentUser, db: SessionDep) -> Page[CategoryOut]:
    service.ensure_can_include_inactive(user, params.include_inactive)
    return await service.list_values(db, Category, CategoryOut, params, params.include_inactive)


@categories.post("", response_model=CategoryOut, status_code=201, dependencies=AdminOnly)
async def create_category(data: LookupCreate, db: SessionDep) -> Category:
    return await service.create_value(db, Category, data)


@categories.put("/order", status_code=204, dependencies=AdminOnly)
async def reorder_categories(data: ReorderIn, db: SessionDep) -> None:
    await service.reorder(db, Category, data.ids)


@categories.patch("/{category_id}", response_model=CategoryOut, dependencies=AdminOnly)
async def update_category(category_id: int, data: LookupUpdate, db: SessionDep) -> Category:
    return await service.update_value(db, Category, category_id, data)


@categories.post("/{category_id}/activate", response_model=CategoryOut, dependencies=AdminOnly)
async def activate_category(category_id: int, db: SessionDep) -> Category:
    return await service.set_active(db, Category, category_id, True)


@categories.post("/{category_id}/deactivate", response_model=CategoryOut, dependencies=AdminOnly)
async def deactivate_category(category_id: int, db: SessionDep) -> Category:
    return await service.set_active(db, Category, category_id, False)


# ---------------------------------------------------------------- statuses

statuses = APIRouter(prefix="/statuses", tags=["dropdowns"])


@statuses.get("", response_model=Page[StatusOut])
async def list_statuses(params: Query_, user: CurrentUser, db: SessionDep) -> Page[StatusOut]:
    service.ensure_can_include_inactive(user, params.include_inactive)
    return await service.list_values(db, Status, StatusOut, params, params.include_inactive)


@statuses.post("", response_model=StatusOut, status_code=201, dependencies=AdminOnly)
async def create_status(data: StatusCreate, db: SessionDep) -> Status:
    """The first status ever created becomes the default."""
    return await service.create_value(db, Status, data)


@statuses.put("/order", status_code=204, dependencies=AdminOnly)
async def reorder_statuses(data: ReorderIn, db: SessionDep) -> None:
    await service.reorder(db, Status, data.ids)


@statuses.patch("/{status_id}", response_model=StatusOut, dependencies=AdminOnly)
async def update_status(status_id: int, data: StatusUpdate, db: SessionDep) -> Status:
    """Rename, recolor, or toggle `is_done` (the last active done status must stay done)."""
    return await service.update_value(db, Status, status_id, data)


@statuses.post("/{status_id}/activate", response_model=StatusOut, dependencies=AdminOnly)
async def activate_status(status_id: int, db: SessionDep) -> Status:
    return await service.set_active(db, Status, status_id, True)


@statuses.post("/{status_id}/deactivate", response_model=StatusOut, dependencies=AdminOnly)
async def deactivate_status(status_id: int, db: SessionDep) -> Status:
    """Rejected for the default status and for the last active done status."""
    return await service.set_active(db, Status, status_id, False)


@statuses.post("/{status_id}/default", response_model=StatusOut, dependencies=AdminOnly)
async def set_default_status(status_id: int, db: SessionDep) -> Status:
    """Make this (active) status the default; the previous default loses the flag."""
    return await service.set_default(db, Status, status_id)


# ---------------------------------------------------------------- priorities

priorities = APIRouter(prefix="/priorities", tags=["dropdowns"])


@priorities.get("", response_model=Page[PriorityOut])
async def list_priorities(params: Query_, user: CurrentUser, db: SessionDep) -> Page[PriorityOut]:
    service.ensure_can_include_inactive(user, params.include_inactive)
    return await service.list_values(db, Priority, PriorityOut, params, params.include_inactive)


@priorities.post("", response_model=PriorityOut, status_code=201, dependencies=AdminOnly)
async def create_priority(data: LookupCreate, db: SessionDep) -> Priority:
    """The first priority ever created becomes the default."""
    return await service.create_value(db, Priority, data)


@priorities.put("/order", status_code=204, dependencies=AdminOnly)
async def reorder_priorities(data: ReorderIn, db: SessionDep) -> None:
    await service.reorder(db, Priority, data.ids)


@priorities.patch("/{priority_id}", response_model=PriorityOut, dependencies=AdminOnly)
async def update_priority(priority_id: int, data: LookupUpdate, db: SessionDep) -> Priority:
    return await service.update_value(db, Priority, priority_id, data)


@priorities.post("/{priority_id}/activate", response_model=PriorityOut, dependencies=AdminOnly)
async def activate_priority(priority_id: int, db: SessionDep) -> Priority:
    return await service.set_active(db, Priority, priority_id, True)


@priorities.post("/{priority_id}/deactivate", response_model=PriorityOut, dependencies=AdminOnly)
async def deactivate_priority(priority_id: int, db: SessionDep) -> Priority:
    """Rejected for the default priority."""
    return await service.set_active(db, Priority, priority_id, False)


@priorities.post("/{priority_id}/default", response_model=PriorityOut, dependencies=AdminOnly)
async def set_default_priority(priority_id: int, db: SessionDep) -> Priority:
    """Make this (active) priority the default; the previous default loses the flag."""
    return await service.set_default(db, Priority, priority_id)
