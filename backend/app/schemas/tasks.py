"""Tasks: a user's own to-do items."""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.core.pagination import PaginationParams

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)]


class TaskState(StrEnum):
    OPEN = "open"
    COMPLETED = "completed"


class TaskSort(StrEnum):
    """`priority` = highest first, `-priority` = lowest first.

    Priorities are ranked by the admin's dropdown order, lowest first: the last value
    in the list is the highest priority.
    """

    DUE_DATE = "due_date"
    DUE_DATE_DESC = "-due_date"
    PRIORITY = "priority"
    PRIORITY_DESC = "-priority"
    CREATED = "created_at"
    CREATED_DESC = "-created_at"


class TaskQuery(PaginationParams):
    """Pagination plus filters. All filters combine with AND."""

    status_id: int | None = None
    priority_id: int | None = None
    project_id: int | None = None
    category_id: int | None = None
    due_from: date | None = None
    """Due on or after this date (tasks without a due date are excluded)."""
    due_to: date | None = None
    """Due on or before this date (tasks without a due date are excluded)."""
    state: TaskState | None = None
    """`open`: status is not done. `completed`: status counts as done."""
    sort: TaskSort = TaskSort.DUE_DATE

    @model_validator(mode="after")
    def _due_range(self) -> Self:
        if self.due_from and self.due_to and self.due_from > self.due_to:
            raise ValueError("due_from must not be after due_to")
        return self


# ---------------------------------------------------------------- output


class LookupRef(BaseModel):
    """A category or priority as embedded in a record (it may be inactive by now)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    color: str | None
    is_active: bool


class StatusRef(LookupRef):
    is_done: bool


class ProjectRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool


class TaskOut(BaseModel):
    id: int
    title: str
    description: str | None
    project: ProjectRef | None
    category: LookupRef | None
    status: StatusRef
    priority: LookupRef
    due_date: date | None
    completed_at: datetime | None
    is_overdue: bool
    """Due before today (APP_TIMEZONE) and not done."""
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- input


class TaskCreate(BaseModel):
    """Omitted status/priority get the default value."""

    title: Title
    description: Description | None = None
    project_id: int | None = None
    category_id: int | None = None
    status_id: int | None = None
    priority_id: int | None = None
    due_date: date | None = None


class TaskUpdate(BaseModel):
    """Omitted fields keep their value. Send null to clear an optional field.

    A value that has been deactivated may be kept (sent unchanged) but not newly chosen.
    """

    title: Title | None = None
    description: Description | None = None
    project_id: int | None = None
    category_id: int | None = None
    status_id: int | None = None
    priority_id: int | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def _required_not_null(self) -> Self:
        for name in ("title", "status_id", "priority_id"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self
