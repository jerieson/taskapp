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

LogDraftField = Literal["title", "log_date", "hours_spent", "category_id"]
"""Fields a prod log needs that the draft may lack."""


class LogDraftRequest(BaseModel):
    text: DraftText
    """Free text describing the work, e.g. "2h yesterday on the login bug"."""


class LogDraftOut(BaseModel):
    """A prod log draft for the user to review. Every ID is active and usable by the
    caller; anything the AI could not determine is null and listed in `missing_fields`."""

    title: str | None
    description: str | None
    log_date: date | None
    hours_spent: HoursOut | None
    task_id: int | None
    """One of the caller's own open tasks."""
    project_id: int | None
    category_id: int | None
    missing_fields: list[LogDraftField]
    """Required fields that are still null; the form highlights them."""
