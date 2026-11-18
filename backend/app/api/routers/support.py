"""Support dictionary: everyone reads and adds entries; the author or an admin edits
and (de)activates them. Entries are never deleted."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser
from app.core.pagination import Page
from app.db.session import SessionDep
from app.schemas.support import (
    SupportEntryCreate,
    SupportEntryOut,
    SupportEntryUpdate,
    SupportFacets,
    SupportQuery,
)
from app.services import support as service

router = APIRouter(prefix="/support", tags=["support"])


@router.get("", response_model=Page[SupportEntryOut])
async def list_entries(
    params: Annotated[SupportQuery, Query()], user: CurrentUser, db: SessionDep
) -> Page[SupportEntryOut]:
    return await service.list_entries(db, user, params)


@router.get("/facets", response_model=SupportFacets)
async def get_facets(user: CurrentUser, db: SessionDep) -> SupportFacets:
    """Distinct projects, modules and sub-modules of active entries."""
    return await service.facets(db)


@router.post("", response_model=SupportEntryOut, status_code=201)
async def create_entry(
    data: SupportEntryCreate, user: CurrentUser, db: SessionDep
) -> SupportEntryOut:
    return await service.create_entry(db, user, data)


@router.get("/{entry_id}", response_model=SupportEntryOut)
async def get_entry(entry_id: int, user: CurrentUser, db: SessionDep) -> SupportEntryOut:
    return await service.get_entry(db, user, entry_id)


@router.patch("/{entry_id}", response_model=SupportEntryOut)
async def update_entry(
    entry_id: int, data: SupportEntryUpdate, user: CurrentUser, db: SessionDep
) -> SupportEntryOut:
    """Author or admin only (403 `not_author` otherwise)."""
    return await service.update_entry(db, user, entry_id, data)


@router.post("/{entry_id}/activate", response_model=SupportEntryOut)
async def activate_entry(entry_id: int, user: CurrentUser, db: SessionDep) -> SupportEntryOut:
    return await service.set_active(db, user, entry_id, True)


@router.post("/{entry_id}/deactivate", response_model=SupportEntryOut)
async def deactivate_entry(entry_id: int, user: CurrentUser, db: SessionDep) -> SupportEntryOut:
    """Hidden from the list unless `include_inactive=true`."""
    return await service.set_active(db, user, entry_id, False)
