"""Prod logs through the normal endpoints: own logs for everyone; admins can also read,
change and delete anyone's log; managers can read their team's logs (team snapshot)."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query, Response

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser
from app.core.pagination import Page
from app.db.session import SessionDep
from app.schemas.prod_logs import (
    CopyLogs,
    CopyResult,
    LogExportQuery,
    ProdLogBulkCreate,
    ProdLogBulkResult,
    ProdLogCreate,
    ProdLogListItem,
    ProdLogOut,
    ProdLogQuery,
    ProdLogUpdate,
)
from app.services import log_export
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
    """Rejected (422 `daily_hours_exceeded`) if the day would total more than
    WORKDAY_HOURS actual or WORKDAY_HOURS planned hours, and (422 `week_locked`) for
    planned hours in a locked week."""
    return await service.create_log(db, user, data, settings)


@router.post("/bulk", response_model=ProdLogBulkResult, status_code=201)
async def create_logs(
    data: ProdLogBulkCreate, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> ProdLogBulkResult:
    """Create several of your rows at once: all or none. Same checks as a single create,
    with field errors keyed by row index (`rows.2.category_id`)."""
    return await service.create_logs(db, user, data, settings)


@router.post("/copy", response_model=CopyResult)
async def copy_logs(
    data: CopyLogs, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> CopyResult:
    """Copy your rows from a week into days of open weeks (by weekday), as planned rows.

    Every target date must be in an open week (422 `week_locked`). Days that would pass
    WORKDAY_HOURS planned, and rows with inactive values, are skipped and reported. No
    source rows: 422 `nothing_to_copy`."""
    return await service.copy_logs(db, user, data, settings)


@router.get(
    "/export",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV file"}},
)
async def export_logs(
    params: Annotated[LogExportQuery, Query()],
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
) -> Response:
    """One person's logs as a CSV attachment in the team sheet's column order.

    Own logs for everyone; managers: a member's rows written under their team; admins:
    anyone. Other users: 404."""
    filename, content = await log_export.export_csv(db, user, params, settings)
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )


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
