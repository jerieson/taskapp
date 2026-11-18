"""Weekly planning status: planned hours per day for a week (Monday to Friday) and
whether its plan was made before the deadline on the Friday before."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.prod_logs import HoursOut, TeamMemberOut


class PlanWeekQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week: date | None = None
    """Any date in the week (it is moved back to that week's Monday). Omitted: next
    week (the one starting on the next Monday)."""


class PlanDay(BaseModel):
    date: date
    planned_hours: HoursOut


class PlanWeekOut(BaseModel):
    week_start: date
    """Monday."""
    week_end: date
    """Friday."""
    deadline: datetime
    """When the plan is due (UTC): PLAN_DEADLINE_TIME on the Friday before, in
    APP_TIMEZONE."""
    is_open: bool
    """True before the deadline: planned hours can still be entered and changed."""
    workday_hours: HoursOut


class PlanningStatus(PlanWeekOut):
    """The caller's own plan for the week."""

    days: list[PlanDay]
    """Monday to Friday."""
    total: HoursOut
    has_planned: bool
    """At least one row with planned hours in the week."""
    show_reminder: bool
    """It is the Friday before the week, before the deadline, and nothing is planned."""


class MemberPlan(BaseModel):
    member: TeamMemberOut
    days: list[PlanDay]
    """Monday to Friday."""
    total: HoursOut
    has_planned: bool


class TeamPlanningStatus(PlanWeekOut):
    """Each member's planned hours (by the team snapshot on each row). Members are the
    team's active current members plus anyone with planned rows under the team that
    week, ordered by username."""

    members: list[MemberPlan]
