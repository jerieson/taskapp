"""Prod logs through the normal endpoints: own logs for everyone; admins can also read,
change and delete anyone's log; managers can read their team's logs (team snapshot)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser
from app.core.pagination import Page
from app.db.session import SessionDep
from app.schemas.prod_logs import (
    ProdLogCreate,
    ProdLogListItem,
    ProdLogOut,
    ProdLogQuery,
    ProdLogUpdate,
)
from app.services import prod_logs as service

router = APIRouter(prefix="/logs", tags=["prod logs"])


@router.get("", response_model=Page[ProdLogListItem])
async def list_logs(
    params: Annotated[ProdLogQuery, Query()], user: CurrentUser, db: SessionDep
) -> Page[ProdLogListItem]:
    """The caller's own logs, newest date first."""
    return await service.list_logs(db, user, params)


@router.post("", response_model=ProdLogOut, status_code=201)
async def create_log(data: ProdLogCreate, user: CurrentUser, db: SessionDep) -> ProdLogOut:
    """Rejected (422 `daily_hours_exceeded`) if the day would total more than 24 hours."""
    return await service.create_log(db, user, data)


@router.get("/{log_id}", response_model=ProdLogOut)
async def get_log(log_id: int, user: CurrentUser, db: SessionDep) -> ProdLogOut:
    return await service.get_log(db, user, log_id)


@router.patch("/{log_id}", response_model=ProdLogOut)
async def update_log(
    log_id: int, data: ProdLogUpdate, user: CurrentUser, db: SessionDep
) -> ProdLogOut:
    """Partial update by the author or an admin. The team snapshot never changes."""
    return await service.update_log(db, user, log_id, data)


@router.delete("/{log_id}", status_code=204)
async def delete_log(log_id: int, user: CurrentUser, db: SessionDep) -> None:
    await service.delete_log(db, user, log_id)
