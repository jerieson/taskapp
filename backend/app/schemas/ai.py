"""AI features: request and response bodies. Nothing here is saved; the user confirms
AI drafts through the normal endpoints."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationInfo, field_validator

from app.core.pagination import PaginationParams
from app.schemas.prod_logs import HoursOut, UserRef

LOG_DRAFT_MAX_CHARS = 2000
LOG_DRAFT_MAX_ROWS = 20

DraftText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LOG_DRAFT_MAX_CHARS)
]

LogDraftField = Literal["work_setup_id", "category_id", "project_id", "activity_id", "hours"]
"""Fields a prod log needs that the draft may lack. `hours`: neither planned nor actual
hours, or hours the user should check (whether they were per day or per week was
unclear)."""


class LogDraftRequest(BaseModel):
    text: DraftText
    """Free text describing the work, e.g. "2h yesterday on the login bug" or "I will work
    on the workforce API next week Tuesday to Friday, 4 hrs a day"."""


class LogDraftRow(BaseModel):
    """One prod log row for the user to review. Every ID is active and usable by the
    caller and fits the linked-dropdown rules; anything the AI could not determine is
    null, and required ones are listed in `missing_fields`."""

    log_date: date
    is_planned: bool
    """Planned unless the text says the work was unplanned, or planned hours in a locked
    week were turned into actual hours."""
    work_setup_id: int | None
    """The default work set-up unless the text says otherwise."""
    planned_hours: HoursOut | None
    hours_spent: HoursOut | None
    category_id: int | None
    project_id: int | None
    """Linked to the category."""
    activity_id: int | None
    """Offered for the project (its activity group)."""
    om_project_id: int | None
    """Only when the category offers "Project (For O&M)"."""
    description: str | None
    missing_fields: list[LogDraftField]
    """Required fields that are still null (or hours to check); the form highlights
    them."""


class LogDraftOut(BaseModel):
    rows: list[LogDraftRow]
    """At most LOG_DRAFT_MAX_ROWS, in date order. Empty when the text described no work
    with a usable date. Save them with POST /api/logs/bulk."""


# ---------------------------------------------------------------- team summary

TEAM_SUMMARY_MAX_DAYS = 366


class TeamSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: int
    period_start: date
    """First day of the period (inclusive)."""
    period_end: date
    """Last day of the period (inclusive)."""
    regenerate: bool = False
    """False: return the saved summary for this team and period if there is one (no AI
    call). True: always ask the AI for a new one."""

    @field_validator("period_end")
    @classmethod
    def _period(cls, end: date, info: ValidationInfo) -> date:
        start = info.data.get("period_start")
        if start is None:
            return end
        if end < start:
            raise ValueError("The period must not end before it starts")
        if (end - start).days >= TEAM_SUMMARY_MAX_DAYS:
            raise ValueError(f"The period can be at most {TEAM_SUMMARY_MAX_DAYS} days")
        return end


class TeamSummaryQuery(PaginationParams):
    team_id: int


class TeamSummaryOut(BaseModel):
    """A saved AI team summary. The text is markdown written by the AI; numbers in it
    were copied from the database figures it was given."""

    id: int
    team_id: int
    period_start: date
    period_end: date
    summary_text: str
    provider: str
    model: str
    requested_by: UserRef
    created_at: datetime


class TeamSummaryStats(BaseModel):
    """Database figures for the team and period (team snapshot on each log), computed
    when the response is built."""

    actual_hours: HoursOut
    """Actual hours (rows with actual hours only)."""
    planned_hours: HoursOut
    """Planned hours of all rows in the period."""
    unplanned_hours: HoursOut
    """Actual hours on rows marked Unplanned."""
    log_rows: int
    """Log rows in the period (planned and actual)."""
    members_with_hours: int
    """People with actual hours in the period."""
    deviation_rows: int
    """Rows with a reason for deviation."""


class TeamSummaryResult(TeamSummaryOut):
    cached: bool
    """True when this is a saved summary returned without calling the AI."""
    stats: TeamSummaryStats
