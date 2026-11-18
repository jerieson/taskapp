"""AI features: request and response bodies. Nothing here is saved; the user confirms
AI drafts through the normal endpoints."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.schemas.prod_logs import HoursOut

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
