"""Prod logs through the normal endpoints: own logs for everyone; admins can also read,
change and delete anyone's log; managers can read their team's logs (team snapshot)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser
from app.core.pagination import Page
from app.db.session import SessionDep
from app.schemas.prod_logs import (
    CopyLogs,
    CopyResult,
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
async def create_log(
    data: ProdLogCreate, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> ProdLogOut:
    """Rejected (422 `daily_hours_exceeded`) if the day would total more than 24 actual
    or 24 planned hours, and (422 `week_locked`) for planned hours in a locked week."""
    return await service.create_log(db, user, data, settings)


@router.post("/copy", response_model=CopyResult)
async def copy_logs(
    data: CopyLogs, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> CopyResult:
    """Copy your rows from a day or a week into days of open weeks, as planned rows.

    Every target date must be in an open week (422 `week_locked`). Days that would pass
    24 planned hours, and rows with inactive values, are skipped and reported. No source
    rows: 422 `nothing_to_copy`."""
    return await service.copy_logs(db, user, data, settings)


@router.get("/{log_id}", response_model=ProdLogOut)
async def get_log(log_id: int, user: CurrentUser, db: SessionDep) -> ProdLogOut:
    return await service.get_log(db, user, log_id)


@router.patch("/{log_id}", response_model=ProdLogOut)
async def update_log(
    log_id: int, data: ProdLogUpdate, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> ProdLogOut:
    """Partial update by the author or an admin. The team snapshot never changes."""
    return await service.update_log(db, user, log_id, data, settings)


@router.delete("/{log_id}", status_code=204)
async def delete_log(log_id: int, user: CurrentUser, db: SessionDep, settings: SettingsDep) -> None:
    """Planned rows in a locked week can only be deleted by an admin (422 `week_locked`)."""
    await service.delete_log(db, user, log_id, settings)
