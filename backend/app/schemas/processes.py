"""Personal processes (reusable step templates) and their runs."""

from datetime import date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.core.pagination import PaginationParams
from app.models import RunStatus
from app.schemas.prod_logs import Hours, HoursOut
from app.schemas.tasks import Description, LookupRef, TaskOut, Title

MAX_STEPS = 100

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


# ---------------------------------------------------------------- queries


class ProcessQuery(PaginationParams):
    is_active: bool | None = None
    """true: active processes only; false: deactivated only; omitted: both."""


class RunQuery(PaginationParams):
    status: RunStatus | None = None


# ---------------------------------------------------------------- output


class ProcessStepOut(BaseModel):
    id: int
    step_order: int
    """Position in the process, starting at 0."""
    title: str
    description: str | None
    default_category: LookupRef | None
    estimated_hours: HoursOut | None


class ProcessListItem(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    step_count: int
    run_count: int
    """All runs, whatever their status."""
    active_run_count: int
    """Runs still in progress."""
    created_at: datetime
    updated_at: datetime


class ProcessOut(ProcessListItem):
    steps: list[ProcessStepOut]
    """In step order."""


class ProcessRef(BaseModel):
    id: int
    name: str
    is_active: bool


class RunProgress(BaseModel):
    done: int
    """Tasks of the run whose status counts as done."""
    total: int


class RunOut(BaseModel):
    id: int
    process: ProcessRef
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None
    progress: RunProgress


class RunDetail(RunOut):
    tasks: list[TaskOut]
    """The run's tasks in step order (as copied when the run started)."""


# ---------------------------------------------------------------- input


class StepCreate(BaseModel):
    title: Title
    description: Description | None = None
    default_category_id: int | None = None
    estimated_hours: Hours | None = None


class StepUpdate(BaseModel):
    """Omitted fields keep their value. Send null to clear an optional field."""

    title: Title | None = None
    description: Description | None = None
    default_category_id: int | None = None
    estimated_hours: Hours | None = None

    @model_validator(mode="after")
    def _title_not_null(self) -> Self:
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        return self


class StepSync(StepCreate):
    """A step in the complete list: with `id` it updates that step, without it adds one."""

    id: int | None = None


class StepsSync(BaseModel):
    """The process's complete step list in the new order. Existing steps left out are
    deleted (tasks already copied from them keep their content)."""

    steps: Annotated[list[StepSync], Field(max_length=MAX_STEPS)]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        ids = [step.id for step in self.steps if step.id is not None]
        if len(set(ids)) != len(ids):
            raise ValueError("A step can appear only once")
        return self


class StepOrder(BaseModel):
    """Every step of the process, in the new order."""

    step_ids: Annotated[list[int], Field(max_length=MAX_STEPS)]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        if len(set(self.step_ids)) != len(self.step_ids):
            raise ValueError("step_ids must not repeat")
        return self


class ProcessCreate(BaseModel):
    name: Name
    description: Description | None = None
    steps: Annotated[list[StepCreate], Field(max_length=MAX_STEPS)] = []
    """Initial steps, in order."""


class ProcessUpdate(BaseModel):
    """Omitted fields keep their value. Steps are changed through the step endpoints."""

    name: Name | None = None
    description: Description | None = None

    @model_validator(mode="after")
    def _name_not_null(self) -> Self:
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class RunCreate(BaseModel):
    due_date: date | None = None
    """Set as the due date of every task the run creates."""
