"""AI features: request and response bodies. Nothing here is saved; the user confirms
AI drafts through the normal endpoints."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.schemas.prod_logs import HoursOut

LOG_DRAFT_MAX_CHARS = 2000

DraftText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LOG_DRAFT_MAX_CHARS)
]

LogDraftField = Literal[
    "log_date", "work_setup_id", "category_id", "project_id", "activity_id", "hours"
]
"""Fields a prod log needs that the draft may lack. `hours`: neither planned nor actual
hours."""


class LogDraftRequest(BaseModel):
    text: DraftText
    """Free text describing the work, e.g. "2h yesterday on the login bug"."""


class LogDraftOut(BaseModel):
    """A prod log draft for the user to review. Every ID is active and usable by the
    caller and fits the linked-dropdown rules; anything the AI could not determine is
    null, and required ones are listed in `missing_fields`."""

    log_date: date | None
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
    """Required fields that are still null; the form highlights them."""
