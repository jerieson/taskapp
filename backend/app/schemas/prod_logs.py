"""Prod logs: daily records of time spent, and the team view of them."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator

from app.core.pagination import PaginationParams
from app.schemas.tasks import Description, LookupRef, ProjectRef, Title

MAX_DAILY_HOURS = Decimal(24)

Hours = Annotated[
    Decimal,
    Field(gt=0, le=MAX_DAILY_HOURS, max_digits=4, decimal_places=2, examples=[1.5]),
]
"""Hours on one log: more than 0, at most 24, in steps of 0.01."""

# Hours are NUMERIC in the database; send them to clients as plain JSON numbers.
HoursOut = Annotated[Decimal, PlainSerializer(float, return_type=float)]


class _DateRange(PaginationParams):
    date_from: date | None = None
    """Logs on or after this date."""
    date_to: date | None = None
    """Logs on or before this date."""
    project_id: int | None = None
    category_id: int | None = None

    @model_validator(mode="after")
    def _range(self) -> Self:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self


class ProdLogQuery(_DateRange):
    """The caller's own logs. All filters combine with AND."""

    task_id: int | None = None


class TeamLogQuery(_DateRange):
    """A team's logs (by the team snapshot on each log). All filters combine with AND."""

    user_id: int | None = None
    """Only logs written by this member."""


# ---------------------------------------------------------------- output


class UserRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class TaskRef(BaseModel):
    id: int
    title: str


class ProdLogOut(BaseModel):
    id: int
    user: UserRef
    """The author."""
    team_id: int | None
    """The author's team when the log was created. Never changes."""
    log_date: date
    title: str
    description: str | None
    task_id: int | None
    task: TaskRef | None
    """The linked task. Only included for the author: tasks are private to their owner."""
    project: ProjectRef | None
    category: LookupRef
    hours_spent: HoursOut
    updated_by: UserRef
    """Last person to create or change the log. Differs from `user` after an admin edit."""
    created_at: datetime
    updated_at: datetime


class ProdLogListItem(ProdLogOut):
    day_total_hours: HoursOut
    """Total hours of all logs matching the filters on this log's date (across pages)."""


class TeamMemberOut(BaseModel):
    """Someone who can appear in a team's logs: a current member, or a former member
    with logs under this team."""

    id: int
    username: str
    is_active: bool
    is_current_member: bool


# ---------------------------------------------------------------- input


class ProdLogCreate(BaseModel):
    """When `task_id` is given and project/category are omitted, they are copied from
    the task (if those values are still active)."""

    log_date: date
    title: Title
    description: Description | None = None
    hours_spent: Hours
    task_id: int | None = None
    project_id: int | None = None
    category_id: int | None = None
    """Required unless it can be copied from the task."""


class ProdLogUpdate(BaseModel):
    """Omitted fields keep their value. Send null to clear an optional field.

    A category or project that has been deactivated may be kept but not newly chosen.
    """

    log_date: date | None = None
    title: Title | None = None
    description: Description | None = None
    hours_spent: Hours | None = None
    task_id: int | None = None
    project_id: int | None = None
    category_id: int | None = None

    @model_validator(mode="after")
    def _required_not_null(self) -> Self:
        for name in ("log_date", "title", "hours_spent", "category_id"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self
