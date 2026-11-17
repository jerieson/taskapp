"""The caller's own process runs. Runs are never deleted; cancel instead."""

from datetime import date, datetime

from fastapi import APIRouter

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser
from app.db.session import SessionDep
from app.schemas.processes import RunDetail
from app.services import process_runs as service

router = APIRouter(prefix="/runs", tags=["processes"])


def _today(settings: SettingsDep) -> date:
    return datetime.now(settings.tz).date()


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
