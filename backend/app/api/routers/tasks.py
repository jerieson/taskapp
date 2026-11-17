"""The caller's own tasks. Other users' tasks (for admins too) are 404."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser
from app.core.pagination import Page
from app.db.session import SessionDep
from app.schemas.tasks import TaskCreate, TaskOut, TaskQuery, TaskUpdate
from app.services import tasks as service

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _today(settings: SettingsDep) -> date:
    return datetime.now(settings.tz).date()


@router.get("", response_model=Page[TaskOut])
async def list_tasks(
    params: Annotated[TaskQuery, Query()],
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
) -> Page[TaskOut]:
    return await service.list_tasks(db, user, params, _today(settings))


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    data: TaskCreate, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> TaskOut:
    """Omitted status/priority get the default; only active values are accepted."""
    return await service.create_task(db, user, data, _today(settings))


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: int, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> TaskOut:
    return await service.get_task(db, user, task_id, _today(settings))


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int, data: TaskUpdate, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> TaskOut:
    """Partial update. Changing status sets or clears `completed_at`."""
    return await service.update_task(db, user, task_id, data, _today(settings))


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: int, user: CurrentUser, db: SessionDep) -> None:
    await service.delete_task(db, user, task_id)
