"""Dropdown values, projects, the log form's options and the Data tab import."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.core.pagination import PaginationParams

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
LongLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Color = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^#[0-9A-Fa-f]{6}$"),
    AfterValidator(str.upper),
]
ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ProjectDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
IdList = Annotated[list[int], Field(max_length=500)]


class LookupQuery(PaginationParams):
    """Pagination plus `include_inactive` (admin only; others get active rows only)."""

    include_inactive: bool = False


# ---------------------------------------------------------------- output


class PlainLookupOut(BaseModel):
    """A dropdown value without a color (activity groups, O&M projects)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    sort_order: int
    is_active: bool


class LookupOut(PlainLookupOut):
    color: str | None


class CategoryOut(LookupOut):
    requires_om_project: bool
    """Log rows in this category offer "Project (For O&M)"."""


class ActivityOut(LookupOut):
    pass


class OmProjectOut(PlainLookupOut):
    pass


class ActivityGroupOut(PlainLookupOut):
    activity_ids: list[int]
    """Member activities (active and inactive) in display order."""


class PriorityOut(LookupOut):
    is_default: bool


class WorkSetupOut(PriorityOut):
    pass


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
    category_ids: list[int]
    """Categories this project can be logged under."""
    activity_group_id: int | None
    """The group whose activities can be logged against this project."""


# ---------------------------------------------------------------- input


class LookupCreate(BaseModel):
    label: Label
    color: Color | None = None


class LongLookupCreate(BaseModel):
    label: LongLabel
    color: Color | None = None


class PlainLookupCreate(BaseModel):
    label: Label


class OmProjectCreate(BaseModel):
    label: LongLabel


class CategoryCreate(LookupCreate):
    requires_om_project: bool = False


class StatusCreate(LookupCreate):
    is_done: bool = False


class LookupUpdate(BaseModel):
    """Omitted fields keep their value. Send `"color": null` to clear the color."""

    label: Label | None = None
    color: Color | None = None


class LongLookupUpdate(BaseModel):
    """Omitted fields keep their value. Send `"color": null` to clear the color."""

    label: LongLabel | None = None
    color: Color | None = None


class PlainLookupUpdate(BaseModel):
    label: Label | None = None


class OmProjectUpdate(BaseModel):
    label: LongLabel | None = None


class CategoryUpdate(LookupUpdate):
    requires_om_project: bool | None = None


class StatusUpdate(LookupUpdate):
    is_done: bool | None = None


class ReorderIn(BaseModel):
    """Every row's id (active and inactive) in the new display order."""

    ids: list[int] = Field(min_length=1, max_length=500)


class GroupActivitiesIn(BaseModel):
    """The group's complete, ordered member list. Newly added activities must be active;
    inactive members already in the group may stay."""

    activity_ids: IdList


class ProjectCreate(BaseModel):
    name: ProjectName
    description: ProjectDescription = ""
    category_ids: IdList = []
    activity_group_id: int | None = None


class ProjectUpdate(BaseModel):
    """Omitted fields keep their value. `category_ids` replaces the whole list;
    send `"activity_group_id": null` to clear the group."""

    name: ProjectName | None = None
    description: ProjectDescription | None = None
    category_ids: IdList | None = None
    activity_group_id: int | None = None


# ---------------------------------------------------------------- log form options


class LogOptionProject(BaseModel):
    id: int
    name: str
    category_ids: list[int]
    """Active categories only."""
    activity_group_id: int | None
    """Null when the project has no group or its group is inactive."""


class LogOptionGroup(BaseModel):
    id: int
    label: str
    activity_ids: list[int]
    """Active member activities, in display order."""


class LogOptionsOut(BaseModel):
    """Every active value the log form needs, in display order."""

    categories: list[CategoryOut]
    projects: list[LogOptionProject]
    activity_groups: list[LogOptionGroup]
    activities: list[ActivityOut]
    om_projects: list[OmProjectOut]
    work_setups: list[WorkSetupOut]


# ---------------------------------------------------------------- Data tab import


class ImportCounts(BaseModel):
    categories: int = 0
    projects: int = 0
    activity_groups: int = 0
    activities: int = 0
    om_projects: int = 0


class ImportLinks(BaseModel):
    project_categories: int = 0
    """Projects linked to a category."""
    project_groups: int = 0
    """Projects given an activity group."""
    group_activities: int = 0
    """Activities added to a group."""
    om_flags: int = 0
    """Categories that now offer "Project (For O&M)"."""


class GroupConflict(BaseModel):
    project: str
    current_group: str
    file_group: str


class DataTabImportOut(BaseModel):
    created: ImportCounts
    linked: ImportLinks
    group_conflicts: list[GroupConflict]
    """Projects that already have a different group; kept unchanged."""
    unlinked_groups: list[str]
    """Groups imported without a project (their column names no project)."""
    inactive_reused: list[str]
    """Existing inactive values the file mentions; linked but left inactive."""
    unrecognised_columns: list[str]
    empty_columns: list[str]
