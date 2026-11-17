"""Dashboard aggregations. All numbers are computed in SQL; weeks start on Monday and
dates follow APP_TIMEZONE."""

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.prod_logs import HoursOut
from app.schemas.tasks import LookupRef, ProjectRef

WEEKS_IN_TREND = 8

# ---------------------------------------------------------------- queries


class WeekQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week: date | None = None
    """Any date in the week to show (it is moved back to that week's Monday).
    Omitted: the current week."""


class DateRangeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: date
    """First day of the range (inclusive)."""
    date_to: date
    """Last day of the range (inclusive)."""

    @model_validator(mode="after")
    def _range(self) -> Self:
        if self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self


# ---------------------------------------------------------------- output


class DayHours(BaseModel):
    date: date
    hours: HoursOut


class HoursPerDay(BaseModel):
    week_start: date
    """The Monday of the week."""
    week_end: date
    """The Sunday of the week."""
    days: list[DayHours]
    """All seven days, Monday first; days without logs have 0 hours."""
    total: HoursOut


class WeekHours(BaseModel):
    week_start: date
    """The Monday of the week."""
    hours: HoursOut


class HoursPerWeek(BaseModel):
    weeks: list[WeekHours]
    """The last 8 weeks, oldest first, ending with the current week; weeks without
    logs have 0 hours."""


class ProjectHours(BaseModel):
    project: ProjectRef | None
    """null: logs without a project."""
    hours: HoursOut


class HoursByProject(BaseModel):
    date_from: date
    date_to: date
    items: list[ProjectHours]
    """Most hours first. Only projects with hours in the range are listed."""
    total: HoursOut


class CategoryHours(BaseModel):
    category: LookupRef
    hours: HoursOut


class HoursByCategory(BaseModel):
    date_from: date
    date_to: date
    items: list[CategoryHours]
    """Most hours first. Only categories with hours in the range are listed."""
    total: HoursOut


class TaskCounts(BaseModel):
    date_from: date
    date_to: date
    completed: int
    """Tasks completed within the range (and still done)."""
    open: int
    """Tasks open now (status not done), whatever the range."""
    overdue: int
    """Open tasks whose due date is before today."""
