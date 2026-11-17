"""Dropdown values (categories, statuses, priorities) and projects."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.core.pagination import PaginationParams

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Color = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^#[0-9A-Fa-f]{6}$"),
    AfterValidator(str.upper),
]
ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ProjectDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class LookupQuery(PaginationParams):
    """Pagination plus `include_inactive` (admin only; others get active rows only)."""

    include_inactive: bool = False


# ---------------------------------------------------------------- output


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    color: str | None
    sort_order: int
    is_active: bool


class PriorityOut(CategoryOut):
    is_default: bool


class StatusOut(PriorityOut):
    is_done: bool
    """Tasks with this status count as completed."""


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------- input


class LookupCreate(BaseModel):
    label: Label
    color: Color | None = None


class StatusCreate(LookupCreate):
    is_done: bool = False


class LookupUpdate(BaseModel):
    """Omitted fields keep their value. Send `"color": null` to clear the color."""

    label: Label | None = None
    color: Color | None = None


class StatusUpdate(LookupUpdate):
    is_done: bool | None = None


class ReorderIn(BaseModel):
    """Every row's id (active and inactive) in the new display order."""

    ids: list[int] = Field(min_length=1, max_length=500)


class ProjectCreate(BaseModel):
    name: ProjectName
    description: ProjectDescription = ""


class ProjectUpdate(BaseModel):
    """Omitted fields keep their value."""

    name: ProjectName | None = None
    description: ProjectDescription | None = None
