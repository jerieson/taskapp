"""Prod logs: rows of the productivity log (planned and actual hours), and the team
view of them."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    model_validator,
)

from app.core.pagination import PaginationParams
from app.schemas.tasks import Description, LookupRef, ProjectRef, Title

MAX_DAILY_HOURS = Decimal(24)

Hours = Annotated[
    Decimal,
    Field(gt=0, le=MAX_DAILY_HOURS, max_digits=4, decimal_places=2, examples=[1.5]),
]
"""Hours on one log: more than 0, at most 24, in steps of 0.01."""

DeviationReason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]

# Hours are NUMERIC in the database; send them to clients as plain JSON numbers.
HoursOut = Annotated[Decimal, PlainSerializer(float, return_type=float)]


class _DateRange(PaginationParams):
    date_from: date | None = None
    """Logs on or after this date."""
    date_to: date | None = None
    """Logs on or before this date."""
    project_id: int | None = None
    category_id: int | None = None
    activity_id: int | None = None

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


class PlainRef(BaseModel):
    """A dropdown value without a color (an O&M project) as embedded in a record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    is_active: bool


class ProdLogOut(BaseModel):
    id: int
    user: UserRef
    """The author."""
    team_id: int | None
    """The author's team when the log was created. Never changes."""
    log_date: date
    work_setup: LookupRef
    is_planned: bool
    """Planned ahead of time (true) or unplanned (false)."""
    planned_hours: HoursOut | None
    hours_spent: HoursOut | None
    """Actual hours. Null until filled in for a planned row."""
    category: LookupRef
    project: ProjectRef | None
    """Only null on rows created before projects were required."""
    activity: LookupRef
    om_project: PlainRef | None
    """"Project (For O&M)"; only for categories that offer it."""
    task_id: int | None
    task: TaskRef | None
    """The linked task. Only included for the author: tasks are private to their owner."""
    title: str | None
    """A short note."""
    description: str | None
    """Remarks."""
    deviation_reason: str | None
    updated_by: UserRef
    """Last person to create or change the log. Differs from `user` after an admin edit."""
    created_at: datetime
    updated_at: datetime


class ProdLogListItem(ProdLogOut):
    day_total_hours: HoursOut
    """Total actual hours of all logs matching the filters on this log's date (across
    pages)."""
    day_planned_hours: HoursOut
    """Total planned hours of the same logs."""


class TeamMemberOut(BaseModel):
    """Someone who can appear in a team's logs: a current member, or a former member
    with logs under this team."""

    id: int
    username: str
    is_active: bool
    is_current_member: bool


# ---------------------------------------------------------------- input


class ProdLogCreate(BaseModel):
    """A row needs planned hours, actual hours, or both.

    The linked dropdowns must fit together: the project is linked to the category, the
    activity is in the project's activity group, and an O&M project is only allowed when
    the category offers it. When `task_id` is given and project/category are omitted,
    they are copied from the task (if those values are still active). An omitted work
    set-up is the default one.
    """

    log_date: date
    work_setup_id: int | None = None
    planned_hours: Hours | None = None
    hours_spent: Hours | None = None
    category_id: int | None = None
    """Required unless it can be copied from the task."""
    project_id: int | None = None
    """Required unless it can be copied from the task."""
    activity_id: int
    om_project_id: int | None = None
    task_id: int | None = None
    title: Title | None = None
    description: Description | None = None
    deviation_reason: DeviationReason | None = None


class ProdLogUpdate(BaseModel):
    """Omitted fields keep their value. Send null to clear an optional field.

    A value that has been deactivated (or a link the admin has since removed) may be
    kept but not newly chosen. The row must keep planned hours, actual hours, or both.
    """

    log_date: date | None = None
    work_setup_id: int | None = None
    planned_hours: Hours | None = None
    hours_spent: Hours | None = None
    category_id: int | None = None
    project_id: int | None = None
    activity_id: int | None = None
    om_project_id: int | None = None
    task_id: int | None = None
    title: Title | None = None
    description: Description | None = None
    deviation_reason: DeviationReason | None = None

    @model_validator(mode="after")
    def _required_not_null(self) -> Self:
        required = ("log_date", "work_setup_id", "category_id", "project_id", "activity_id")
        for name in required:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self
