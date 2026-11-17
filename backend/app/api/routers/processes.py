"""The caller's own processes, their steps, and starting runs. Other users' processes
(for admins too) are 404."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser
from app.core.pagination import Page
from app.db.session import SessionDep
from app.schemas.processes import (
    ProcessCreate,
    ProcessListItem,
    ProcessOut,
    ProcessQuery,
    ProcessUpdate,
    RunCreate,
    RunDetail,
    RunOut,
    RunQuery,
    StepCreate,
    StepOrder,
    StepsSync,
    StepUpdate,
)
from app.services import process_runs as run_service
from app.services import processes as service

router = APIRouter(prefix="/processes", tags=["processes"])


def _today(settings: SettingsDep) -> date:
    return datetime.now(settings.tz).date()


@router.get("", response_model=Page[ProcessListItem])
async def list_processes(
    params: Annotated[ProcessQuery, Query()], user: CurrentUser, db: SessionDep
) -> Page[ProcessListItem]:
    """Active processes first, then by name."""
    return await service.list_processes(db, user, params)


@router.post("", response_model=ProcessOut, status_code=201)
async def create_process(data: ProcessCreate, user: CurrentUser, db: SessionDep) -> ProcessOut:
    return await service.create_process(db, user, data)


@router.get("/{process_id}", response_model=ProcessOut)
async def get_process(process_id: int, user: CurrentUser, db: SessionDep) -> ProcessOut:
    return await service.get_process(db, user, process_id)


@router.patch("/{process_id}", response_model=ProcessOut)
async def update_process(
    process_id: int, data: ProcessUpdate, user: CurrentUser, db: SessionDep
) -> ProcessOut:
    return await service.update_process(db, user, process_id, data)


@router.delete("/{process_id}", status_code=204)
async def delete_process(process_id: int, user: CurrentUser, db: SessionDep) -> None:
    """Only while the process has no runs (409 `process_has_runs`); deactivate it instead."""
    await service.delete_process(db, user, process_id)


@router.post("/{process_id}/activate", response_model=ProcessOut)
async def activate_process(process_id: int, user: CurrentUser, db: SessionDep) -> ProcessOut:
    return await service.set_active(db, user, process_id, True)


@router.post("/{process_id}/deactivate", response_model=ProcessOut)
async def deactivate_process(process_id: int, user: CurrentUser, db: SessionDep) -> ProcessOut:
    """A deactivated process keeps its runs but cannot start new ones."""
    return await service.set_active(db, user, process_id, False)


# ---------------------------------------------------------------- steps


@router.post("/{process_id}/steps", response_model=ProcessOut, status_code=201)
async def add_step(
    process_id: int, data: StepCreate, user: CurrentUser, db: SessionDep
) -> ProcessOut:
    """Append a step at the end."""
    return await service.add_step(db, user, process_id, data)


@router.put("/{process_id}/steps", response_model=ProcessOut)
async def sync_steps(
    process_id: int, data: StepsSync, user: CurrentUser, db: SessionDep
) -> ProcessOut:
    """Set the complete step list in one transaction: steps with `id` are updated,
    steps without are added, steps left out are deleted."""
    return await service.sync_steps(db, user, process_id, data)


@router.put("/{process_id}/steps/order", response_model=ProcessOut)
async def reorder_steps(
    process_id: int, data: StepOrder, user: CurrentUser, db: SessionDep
) -> ProcessOut:
    """Set the step order. `step_ids` must list every step of the process."""
    return await service.reorder_steps(db, user, process_id, data)


@router.patch("/{process_id}/steps/{step_id}", response_model=ProcessOut)
async def update_step(
    process_id: int, step_id: int, data: StepUpdate, user: CurrentUser, db: SessionDep
) -> ProcessOut:
    return await service.update_step(db, user, process_id, step_id, data)


@router.delete("/{process_id}/steps/{step_id}", status_code=204)
async def delete_step(process_id: int, step_id: int, user: CurrentUser, db: SessionDep) -> None:
    """Tasks already copied from this step into runs are kept."""
    await service.delete_step(db, user, process_id, step_id)


# ---------------------------------------------------------------- runs


@router.get("/{process_id}/runs", response_model=Page[RunOut])
async def list_runs(
    process_id: int,
    params: Annotated[RunQuery, Query()],
    user: CurrentUser,
    db: SessionDep,
) -> Page[RunOut]:
    """Newest first."""
    return await run_service.list_runs(db, user, process_id, params)


@router.post("/{process_id}/runs", response_model=RunDetail, status_code=201)
async def start_run(
    process_id: int, data: RunCreate, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> RunDetail:
    """Create a run and one task per step (default status and priority)."""
    return await run_service.start_run(db, user, process_id, data, _today(settings))
