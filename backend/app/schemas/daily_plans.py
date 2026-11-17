"""Daily plans: an ordered list of the user's own open tasks for one date."""

from datetime import date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.prod_logs import Hours, HoursOut
from app.schemas.tasks import TaskOut

MAX_PLAN_ITEMS = 100


# ---------------------------------------------------------------- output


class PlanItemOut(BaseModel):
    id: int
    item_order: int
    """Position in the plan, starting at 0."""
    suggested_hours: HoursOut | None
    ai_reason: str | None
    task: TaskOut
    """The task as it is now (it may have been completed since it was added)."""


class DailyPlanOut(BaseModel):
    id: int
    plan_date: date
    ai_generated: bool
    created_at: datetime
    items: list[PlanItemOut]
    """In plan order."""
    total_hours: HoursOut
    """Sum of `suggested_hours` over all items."""
    workday_hours: HoursOut
    """WORKDAY_HOURS: the planned total the UI compares against."""


# ---------------------------------------------------------------- input


class PlanOpen(BaseModel):
    plan_date: date


class PlanItemCreate(BaseModel):
    """The task must be one of the caller's own open tasks, not already in the plan."""

    task_id: int
    suggested_hours: Hours | None = None


class PlanItemUpdate(BaseModel):
    suggested_hours: Hours | None
    """Send null to clear."""


class PlanOrder(BaseModel):
    """Every item of the plan, in the new order."""

    item_ids: Annotated[list[int], Field(max_length=MAX_PLAN_ITEMS)]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        if len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError("item_ids must not repeat")
        return self


class PlanItemsReplace(BaseModel):
    """The plan's complete new item list, in order. Replaces all existing items."""

    items: Annotated[list[PlanItemCreate], Field(max_length=MAX_PLAN_ITEMS)]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        ids = [item.task_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("A task can appear only once in a plan")
        return self
