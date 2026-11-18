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
    deviation_reason: PlainRef | None
    """"Reason for Deviation (if any)"."""
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

    Rows are Planned unless `is_planned` is false. In a locked week (after the Friday
    deadline) only an admin can enter planned hours (422 `week_locked`). The author's
    planned hours on one date may total at most WORKDAY_HOURS, and separately their
    actual hours (422 `daily_hours_exceeded`).

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
    deviation_reason_id: int | None = None
    is_planned: bool = True
    """Planned (default) or Unplanned."""


class ProdLogUpdate(BaseModel):
    """Omitted fields keep their value. Send null to clear an optional field.

    A value that has been deactivated (or a link the admin has since removed) may be
    kept but not newly chosen. The row must keep planned hours, actual hours, or both.
    Planned hours cannot be set, changed or cleared on a date in a locked week (also by
    moving the row to or from such a date), except by an admin (422 `week_locked`).
    Actual hours, Planned/Unplanned, remarks and the reason for deviation can change at
    any time.
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
    deviation_reason_id: int | None = None
    is_planned: bool | None = None
    """Planned or Unplanned."""

    @model_validator(mode="after")
    def _required_not_null(self) -> Self:
        required = (
            "log_date",
            "work_setup_id",
            "category_id",
            "project_id",
            "activity_id",
            "is_planned",
        )
        for name in required:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


# ---------------------------------------------------------------- copy a plan

MAX_COPY_DAYS = 14


class CopyLogs(BaseModel):
    """Copy the caller's rows from one day, or one week, to days in open weeks.

    `from_date`: every row of that day is copied to each of `to_dates`.
    `from_week` (any date in the source week): each row goes to the target date with
    the same weekday (Monday's rows to the Monday in `to_dates`, and so on).
    Copies are planned rows: planned hours = the source's planned hours, else its actual
    hours; no actual hours. Category, project, activity, O&M project, work set-up, task
    and note are kept.
    """

    model_config = ConfigDict(extra="forbid")

    from_date: date | None = None
    from_week: date | None = None
    to_dates: list[date] = Field(min_length=1, max_length=MAX_COPY_DAYS)

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.from_date is None) == (self.from_week is None):
            raise ValueError("Send either from_date or from_week")
        if len(set(self.to_dates)) != len(self.to_dates):
            raise ValueError("to_dates must not repeat a date")
        if self.from_date is not None and self.from_date in self.to_dates:
            raise ValueError("to_dates must not include from_date")
        return self


class CopyDayResult(BaseModel):
    date: date
    created: int
    """Rows created on this date."""
    skipped_reason: str | None
    """`daily_hours_exceeded` (the copies would take the day over 24 planned hours, so
    none were made) or `nothing_to_copy` (no source rows for this date); null when rows
    were created."""


class CopyResult(BaseModel):
    created: int
    """Rows created in total."""
    days: list[CopyDayResult]
    """One entry per target date, in date order."""
    skipped_rows: int
    """Source rows left out because a value on them is inactive or no longer linked
    (or they have no project)."""


# ---------------------------------------------------------------- export

MAX_EXPORT_DAYS = 366


class LogExportQuery(BaseModel):
    """One person's logs as CSV in the sheet's column order."""

    model_config = ConfigDict(extra="forbid")

    date_from: date
    """First day (inclusive)."""
    date_to: date
    """Last day (inclusive). At most 366 days after `date_from`."""
    user_id: int | None = None
    """Whose logs. Omitted: the caller's own. Managers: members of their team (rows
    written under the team); admins: anyone."""

    @model_validator(mode="after")
    def _range(self) -> Self:
        if self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        if (self.date_to - self.date_from).days >= MAX_EXPORT_DAYS:
            raise ValueError(f"The range can be at most {MAX_EXPORT_DAYS} days")
        return self
