"""The caller's own daily plans. Other users' plans (for admins too) are 404."""

from datetime import date, datetime

from fastapi import APIRouter

from app.core.config import SettingsDep
from app.core.dependencies import CurrentUser
from app.db.session import SessionDep
from app.schemas.daily_plans import (
    DailyPlanOut,
    PlanItemCreate,
    PlanItemsReplace,
    PlanItemUpdate,
    PlanOpen,
    PlanOrder,
)
from app.services import daily_plans as service

router = APIRouter(prefix="/plans", tags=["daily plans"])


def _today(settings: SettingsDep) -> date:
    return datetime.now(settings.tz).date()


@router.post("", response_model=DailyPlanOut)
async def open_plan(
    data: PlanOpen, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> DailyPlanOut:
    """Get or create: the caller's plan for `plan_date`, created empty if needed."""
    return await service.open_plan(
        db, user, data.plan_date, _today(settings), settings.workday_hours
    )


@router.get("/by-date/{plan_date}", response_model=DailyPlanOut)
async def get_plan_by_date(
    plan_date: date, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> DailyPlanOut:
    """The caller's plan for a date; 404 if none has been created yet."""
    return await service.get_plan_by_date(
        db, user, plan_date, _today(settings), settings.workday_hours
    )


@router.get("/{plan_id}", response_model=DailyPlanOut)
async def get_plan(
    plan_id: int, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> DailyPlanOut:
    return await service.get_plan(db, user, plan_id, _today(settings), settings.workday_hours)


@router.post("/{plan_id}/items", response_model=DailyPlanOut, status_code=201)
async def add_item(
    plan_id: int,
    data: PlanItemCreate,
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
) -> DailyPlanOut:
    """Append one of the caller's open tasks. 409 `duplicate_task` if already planned."""
    return await service.add_item(db, user, plan_id, data, _today(settings), settings.workday_hours)


@router.put("/{plan_id}/items", response_model=DailyPlanOut)
async def replace_items(
    plan_id: int,
    data: PlanItemsReplace,
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
) -> DailyPlanOut:
    """Replace all items in one transaction (all or nothing)."""
    return await service.replace_items(
        db, user, plan_id, data, _today(settings), settings.workday_hours
    )


@router.put("/{plan_id}/order", response_model=DailyPlanOut)
async def reorder_items(
    plan_id: int,
    data: PlanOrder,
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
) -> DailyPlanOut:
    """Set the item order. `item_ids` must list every item of the plan."""
    return await service.reorder(db, user, plan_id, data, _today(settings), settings.workday_hours)


@router.patch("/{plan_id}/items/{item_id}", response_model=DailyPlanOut)
async def update_item(
    plan_id: int,
    item_id: int,
    data: PlanItemUpdate,
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
) -> DailyPlanOut:
    """Set or clear an item's suggested hours."""
    return await service.update_item(
        db, user, plan_id, item_id, data, _today(settings), settings.workday_hours
    )


@router.delete("/{plan_id}/items/{item_id}", status_code=204)
async def remove_item(plan_id: int, item_id: int, user: CurrentUser, db: SessionDep) -> None:
    await service.remove_item(db, user, plan_id, item_id)
