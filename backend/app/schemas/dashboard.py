"""Dashboard aggregations. All numbers are computed in SQL; weeks start on Monday and
dates follow APP_TIMEZONE. Hours are actual hours (`hours_spent`); rows without actual
hours are left out, except for the planned hours on the personal daily chart."""

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.prod_logs import HoursOut, TeamMemberOut
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


class DayPlannedHours(DayHours):
    planned_hours: HoursOut
    """Planned hours on this day (rows with planned hours, whether or not actual hours
    have been filled in)."""


class PersonalHoursPerDay(HoursPerDay):
    """`hours` and `total` are actual hours; planned hours are alongside."""

    days: list[DayPlannedHours]  # type: ignore[assignment]
    """All seven days, Monday first; days without logs have 0 hours."""
    planned_total: HoursOut


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


class ActivityHours(BaseModel):
    activity: LookupRef
    hours: HoursOut


class HoursByActivity(BaseModel):
    date_from: date
    date_to: date
    items: list[ActivityHours]
    """Most hours first. Only activities with hours in the range are listed."""
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


# ---------------------------------------------------------------- team dashboard
#
# Team numbers come from the team snapshot on each prod log (`prod_logs.team_id`), so
# hours stay with the team they were logged in after the author changes teams.
# "Members" are the team's active current members plus anyone (former members,
# deactivated users) with hours in the period. Task data is counts only.


class MemberDays(BaseModel):
    member: TeamMemberOut
    days: list[DayHours]
    """All seven days, Monday first."""
    total: HoursOut


class TeamHoursPerDay(HoursPerDay):
    members: list[MemberDays]
    """Ordered by username."""


class MemberWeeks(BaseModel):
    member: TeamMemberOut
    weeks: list[WeekHours]
    """The same 8 weeks as the team series, oldest first."""
    total: HoursOut


class TeamHoursPerWeek(HoursPerWeek):
    members: list[MemberWeeks]
    """Ordered by username."""


class MemberHours(BaseModel):
    member: TeamMemberOut
    hours: HoursOut


class HoursByMember(BaseModel):
    date_from: date
    date_to: date
    items: list[MemberHours]
    """Most hours first, then by username; members without hours have 0."""
    total: HoursOut


class MemberTaskCounts(BaseModel):
    member: TeamMemberOut
    completed: int
    """Tasks completed within the range (and still done)."""
    open: int
    """Tasks open now, whatever the range."""
    overdue: int
    """Open tasks whose due date is before today."""


class TeamTaskCounts(BaseModel):
    """Counts only: team views never include task titles or descriptions."""

    date_from: date
    date_to: date
    items: list[MemberTaskCounts]
    """One row per current team member (active ones), ordered by username."""
