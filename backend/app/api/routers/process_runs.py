"""The caller's own process runs. Runs are never deleted; cancel instead."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser
from app.core.pagination import Page
from app.db.session import SessionDep
from app.schemas.processes import RunDetail, RunOut, RunQuery
from app.services import process_runs as service

router = APIRouter(prefix="/runs", tags=["processes"])


def _today(settings: SettingsDep) -> date:
    return datetime.now(settings.tz).date()


@router.get("", response_model=Page[RunOut])
async def list_runs(
    params: Annotated[RunQuery, Query()], user: CurrentUser, db: SessionDep
) -> Page[RunOut]:
    """All of the caller's runs across their processes, newest first."""
    return await service.list_my_runs(db, user, params)


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(
    run_id: int, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> RunDetail:
    """The run with its tasks and progress. Task status changes go through /api/tasks."""
    return await service.get_run(db, user, run_id, _today(settings))


@router.post("/{run_id}/cancel", response_model=RunDetail)
async def cancel_run(
    run_id: int, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> RunDetail:
    """Only runs in progress. The run's tasks are kept."""
    return await service.cancel_run(db, user, run_id, _today(settings))
