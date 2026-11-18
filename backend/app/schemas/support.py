"""Support dictionary: shared entries (known concerns, causes, resolutions, SQL) and the
admin CSV import."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, StringConstraints

from app.core.pagination import PaginationParams
from app.schemas.prod_logs import UserRef
from app.schemas.tasks import LookupRef

# Lengths shared with the CSV import (which reports longer values as row errors).
PLACE_MAX = 100
CONCERN_MAX = 2000
TEXT_MAX = 10000
QUERY_MAX = 20000


def _blank_to_none(value: str | None) -> str | None:
    return value or None


Place = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=PLACE_MAX),
    AfterValidator(_blank_to_none),
]
"""Project, module or sub-module: free text; blank is stored as null."""
Concern = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=CONCERN_MAX)
]
LongText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=TEXT_MAX),
    AfterValidator(_blank_to_none),
]
SqlText = Annotated[
    str,
    # Not stripped on the left: SQL indentation is kept.
    StringConstraints(max_length=QUERY_MAX),
    AfterValidator(lambda v: v.rstrip().lstrip("\r\n") or None),
]
Search = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class SupportQuery(PaginationParams):
    """Search and filters; all combine with AND. Newest first."""

    q: Search | None = None
    """Every word must appear (case-insensitive) in the concern, cause, resolution,
    notes, project, module or sub-module."""
    type_id: int | None = None
    project: Search | None = None
    """Exact project (case-insensitive)."""
    module: Search | None = None
    """Exact module (case-insensitive)."""
    include_inactive: bool = False
    """Also list deactivated entries."""


class SupportEntryOut(BaseModel):
    id: int
    type: LookupRef
    project: str | None
    module: str | None
    sub_module: str | None
    concern: str
    cause: str | None
    resolution: str | None
    query: str | None
    """SQL, shown as code."""
    notes: str | None
    is_active: bool
    created_by: UserRef
    updated_by: UserRef
    created_at: datetime
    updated_at: datetime
    can_edit: bool
    """The caller may edit and (de)activate this entry (author or admin)."""


class SupportEntryCreate(BaseModel):
    type_id: int
    project: Place | None = None
    module: Place | None = None
    sub_module: Place | None = None
    concern: Concern
    cause: LongText | None = None
    resolution: LongText | None = None
    query: SqlText | None = None
    notes: LongText | None = None


class SupportEntryUpdate(BaseModel):
    """Omitted fields keep their value; send null (or blank) to clear an optional
    field. `type_id` and `concern` cannot be cleared."""

    type_id: int | None = None
    project: Place | None = None
    module: Place | None = None
    sub_module: Place | None = None
    concern: Concern | None = None
    cause: LongText | None = None
    resolution: LongText | None = None
    query: SqlText | None = None
    notes: LongText | None = None


class SupportFacets(BaseModel):
    """Distinct values in use (active entries), sorted, for filters and suggestions."""

    projects: list[str]
    modules: list[str]
    sub_modules: list[str]


# ---------------------------------------------------------------- CSV import


class ImportRowError(BaseModel):
    row: int
    """Line number in the file (the header is line 1)."""
    message: str


class TypeMatch(BaseModel):
    file_label: str
    type_label: str


class SupportImportOut(BaseModel):
    dry_run: bool
    """Nothing was saved (preview)."""
    created: int
    skipped: int
    """Rows not imported: blank concern, duplicates and invalid rows."""
    types_created: list[str]
    types_matched: list[TypeMatch]
    """File types matched to an existing type by the start of its label."""
    authors_matched: list[str]
    """Author names matched to a username; those users become the entries' authors."""
    authors_unmatched: list[str]
    """Author names kept in the notes (the importing admin is the author)."""
    errors: list[ImportRowError]
    """Why each skipped row was skipped."""
