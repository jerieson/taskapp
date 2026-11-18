"""Dropdown values: categories, statuses, priorities, work set-ups, activities, activity
groups, O&M projects and reasons for deviation.

Every role can list active values (for selects); only admins write or list inactive
values. There are no delete endpoints: values are deactivated instead.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentUser, require_role
from app.core.pagination import Page
from app.db.session import SessionDep
from app.models import (
    Activity,
    ActivityGroup,
    Category,
    DeviationReason,
    OmProject,
    Priority,
    Role,
    Status,
    WorkSetup,
)
from app.schemas.lookups import (
    ActivityGroupOut,
    ActivityOut,
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    DeviationReasonOut,
    GroupActivitiesIn,
    LongLookupCreate,
    LongLookupUpdate,
    LongPlainLookupCreate,
    LongPlainLookupUpdate,
    LookupCreate,
    LookupQuery,
    LookupUpdate,
    OmProjectCreate,
    OmProjectOut,
    OmProjectUpdate,
    PlainLookupCreate,
    PlainLookupUpdate,
    PriorityOut,
    ReorderIn,
    StatusCreate,
    StatusOut,
    StatusUpdate,
    WorkSetupOut,
)
from app.services import lookups as service

AdminOnly = [Depends(require_role(Role.ADMIN))]
Query_ = Annotated[LookupQuery, Query()]


# ---------------------------------------------------------------- categories

categories = APIRouter(prefix="/categories", tags=["dropdowns"])


@categories.get("", response_model=Page[CategoryOut])
async def list_categories(params: Query_, user: CurrentUser, db: SessionDep) -> Page[CategoryOut]:
    service.ensure_can_include_inactive(user, params.include_inactive)
    return await service.list_values(db, Category, CategoryOut, params, params.include_inactive)


@categories.post("", response_model=CategoryOut, status_code=201, dependencies=AdminOnly)
async def create_category(data: CategoryCreate, db: SessionDep) -> Category:
    return await service.create_value(db, Category, data)


@categories.put("/order", status_code=204, dependencies=AdminOnly)
async def reorder_categories(data: ReorderIn, db: SessionDep) -> None:
    await service.reorder(db, Category, data.ids)


@categories.patch("/{category_id}", response_model=CategoryOut, dependencies=AdminOnly)
async def update_category(category_id: int, data: CategoryUpdate, db: SessionDep) -> Category:
    return await service.update_value(db, Category, category_id, data)


@categories.post("/{category_id}/activate", response_model=CategoryOut, dependencies=AdminOnly)
async def activate_category(category_id: int, db: SessionDep) -> Category:
    return await service.set_active(db, Category, category_id, True)


@categories.post("/{category_id}/deactivate", response_model=CategoryOut, dependencies=AdminOnly)
async def deactivate_category(category_id: int, db: SessionDep) -> Category:
    return await service.set_active(db, Category, category_id, False)


# ---------------------------------------------------------------- statuses

statuses = APIRouter(prefix="/statuses", tags=["dropdowns"])


@statuses.get("", response_model=Page[StatusOut])
async def list_statuses(params: Query_, user: CurrentUser, db: SessionDep) -> Page[StatusOut]:
    service.ensure_can_include_inactive(user, params.include_inactive)
    return await service.list_values(db, Status, StatusOut, params, params.include_inactive)


@statuses.post("", response_model=StatusOut, status_code=201, dependencies=AdminOnly)
async def create_status(data: StatusCreate, db: SessionDep) -> Status:
    """The first status ever created becomes the default."""
    return await service.create_value(db, Status, data)


@statuses.put("/order", status_code=204, dependencies=AdminOnly)
async def reorder_statuses(data: ReorderIn, db: SessionDep) -> None:
    await service.reorder(db, Status, data.ids)


@statuses.patch("/{status_id}", response_model=StatusOut, dependencies=AdminOnly)
async def update_status(status_id: int, data: StatusUpdate, db: SessionDep) -> Status:
    """Rename, recolor, or toggle `is_done` (the last active done status must stay done)."""
    return await service.update_value(db, Status, status_id, data)


@statuses.post("/{status_id}/activate", response_model=StatusOut, dependencies=AdminOnly)
async def activate_status(status_id: int, db: SessionDep) -> Status:
    return await service.set_active(db, Status, status_id, True)


@statuses.post("/{status_id}/deactivate", response_model=StatusOut, dependencies=AdminOnly)
async def deactivate_status(status_id: int, db: SessionDep) -> Status:
    """Rejected for the default status and for the last active done status."""
    return await service.set_active(db, Status, status_id, False)


@statuses.post("/{status_id}/default", response_model=StatusOut, dependencies=AdminOnly)
async def set_default_status(status_id: int, db: SessionDep) -> Status:
    """Make this (active) status the default; the previous default loses the flag."""
    return await service.set_default(db, Status, status_id)


# ---------------------------------------------------------------- priorities

priorities = APIRouter(prefix="/priorities", tags=["dropdowns"])


@priorities.get("", response_model=Page[PriorityOut])
async def list_priorities(params: Query_, user: CurrentUser, db: SessionDep) -> Page[PriorityOut]:
    service.ensure_can_include_inactive(user, params.include_inactive)
    return await service.list_values(db, Priority, PriorityOut, params, params.include_inactive)


@priorities.post("", response_model=PriorityOut, status_code=201, dependencies=AdminOnly)
async def create_priority(data: LookupCreate, db: SessionDep) -> Priority:
    """The first priority ever created becomes the default."""
    return await service.create_value(db, Priority, data)


@priorities.put("/order", status_code=204, dependencies=AdminOnly)
async def reorder_priorities(data: ReorderIn, db: SessionDep) -> None:
    await service.reorder(db, Priority, data.ids)


@priorities.patch("/{priority_id}", response_model=PriorityOut, dependencies=AdminOnly)
async def update_priority(priority_id: int, data: LookupUpdate, db: SessionDep) -> Priority:
    return await service.update_value(db, Priority, priority_id, data)


@priorities.post("/{priority_id}/activate", response_model=PriorityOut, dependencies=AdminOnly)
async def activate_priority(priority_id: int, db: SessionDep) -> Priority:
    return await service.set_active(db, Priority, priority_id, True)


@priorities.post("/{priority_id}/deactivate", response_model=PriorityOut, dependencies=AdminOnly)
async def deactivate_priority(priority_id: int, db: SessionDep) -> Priority:
    """Rejected for the default priority."""
    return await service.set_active(db, Priority, priority_id, False)


@priorities.post("/{priority_id}/default", response_model=PriorityOut, dependencies=AdminOnly)
async def set_default_priority(priority_id: int, db: SessionDep) -> Priority:
    """Make this (active) priority the default; the previous default loses the flag."""
    return await service.set_default(db, Priority, priority_id)


# ---------------------------------------------------------------- work set-ups

work_setups = APIRouter(prefix="/work-setups", tags=["dropdowns"])


@work_setups.get("", response_model=Page[WorkSetupOut])
async def list_work_setups(params: Query_, user: CurrentUser, db: SessionDep) -> Page[WorkSetupOut]:
    service.ensure_can_include_inactive(user, params.include_inactive)
    return await service.list_values(db, WorkSetup, WorkSetupOut, params, params.include_inactive)


@work_setups.post("", response_model=WorkSetupOut, status_code=201, dependencies=AdminOnly)
async def create_work_setup(data: LookupCreate, db: SessionDep) -> WorkSetup:
    """The first work set-up ever created becomes the default."""
    return await service.create_value(db, WorkSetup, data)


@work_setups.put("/order", status_code=204, dependencies=AdminOnly)
async def reorder_work_setups(data: ReorderIn, db: SessionDep) -> None:
    await service.reorder(db, WorkSetup, data.ids)


@work_setups.patch("/{work_setup_id}", response_model=WorkSetupOut, dependencies=AdminOnly)
async def update_work_setup(work_setup_id: int, data: LookupUpdate, db: SessionDep) -> WorkSetup:
    return await service.update_value(db, WorkSetup, work_setup_id, data)


@work_setups.post("/{work_setup_id}/activate", response_model=WorkSetupOut, dependencies=AdminOnly)
async def activate_work_setup(work_setup_id: int, db: SessionDep) -> WorkSetup:
    return await service.set_active(db, WorkSetup, work_setup_id, True)


@work_setups.post(
    "/{work_setup_id}/deactivate", response_model=WorkSetupOut, dependencies=AdminOnly
)
async def deactivate_work_setup(work_setup_id: int, db: SessionDep) -> WorkSetup:
    """Rejected for the default work set-up."""
    return await service.set_active(db, WorkSetup, work_setup_id, False)


@work_setups.post("/{work_setup_id}/default", response_model=WorkSetupOut, dependencies=AdminOnly)
async def set_default_work_setup(work_setup_id: int, db: SessionDep) -> WorkSetup:
    """Make this (active) work set-up the default; the previous default loses the flag."""
    return await service.set_default(db, WorkSetup, work_setup_id)


# ---------------------------------------------------------------- activities

activities = APIRouter(prefix="/activities", tags=["dropdowns"])


@activities.get("", response_model=Page[ActivityOut])
async def list_activities(params: Query_, user: CurrentUser, db: SessionDep) -> Page[ActivityOut]:
    service.ensure_can_include_inactive(user, params.include_inactive)
    return await service.list_values(db, Activity, ActivityOut, params, params.include_inactive)


@activities.post("", response_model=ActivityOut, status_code=201, dependencies=AdminOnly)
async def create_activity(data: LongLookupCreate, db: SessionDep) -> Activity:
    return await service.create_value(db, Activity, data)


@activities.put("/order", status_code=204, dependencies=AdminOnly)
async def reorder_activities(data: ReorderIn, db: SessionDep) -> None:
    await service.reorder(db, Activity, data.ids)


@activities.patch("/{activity_id}", response_model=ActivityOut, dependencies=AdminOnly)
async def update_activity(activity_id: int, data: LongLookupUpdate, db: SessionDep) -> Activity:
    return await service.update_value(db, Activity, activity_id, data)


@activities.post("/{activity_id}/activate", response_model=ActivityOut, dependencies=AdminOnly)
async def activate_activity(activity_id: int, db: SessionDep) -> Activity:
    return await service.set_active(db, Activity, activity_id, True)


@activities.post("/{activity_id}/deactivate", response_model=ActivityOut, dependencies=AdminOnly)
async def deactivate_activity(activity_id: int, db: SessionDep) -> Activity:
    return await service.set_active(db, Activity, activity_id, False)


# ---------------------------------------------------------------- activity groups

activity_groups = APIRouter(prefix="/activity-groups", tags=["dropdowns"])


@activity_groups.get("", response_model=Page[ActivityGroupOut])
async def list_activity_groups(
    params: Query_, user: CurrentUser, db: SessionDep
) -> Page[ActivityGroupOut]:
    service.ensure_can_include_inactive(user, params.include_inactive)
    return await service.list_values(
        db, ActivityGroup, ActivityGroupOut, params, params.include_inactive
    )


@activity_groups.post("", response_model=ActivityGroupOut, status_code=201, dependencies=AdminOnly)
async def create_activity_group(data: PlainLookupCreate, db: SessionDep) -> ActivityGroup:
    return await service.create_value(db, ActivityGroup, data)


@activity_groups.put("/order", status_code=204, dependencies=AdminOnly)
async def reorder_activity_groups(data: ReorderIn, db: SessionDep) -> None:
    await service.reorder(db, ActivityGroup, data.ids)


@activity_groups.patch("/{group_id}", response_model=ActivityGroupOut, dependencies=AdminOnly)
async def update_activity_group(
    group_id: int, data: PlainLookupUpdate, db: SessionDep
) -> ActivityGroup:
    return await service.update_value(db, ActivityGroup, group_id, data)


@activity_groups.put(
    "/{group_id}/activities", response_model=ActivityGroupOut, dependencies=AdminOnly
)
async def set_activity_group_members(
    group_id: int, data: GroupActivitiesIn, db: SessionDep
) -> ActivityGroup:
    """Replace the group's activities with `activity_ids`, in that order."""
    return await service.set_group_activities(db, group_id, data.activity_ids)


@activity_groups.post(
    "/{group_id}/activate", response_model=ActivityGroupOut, dependencies=AdminOnly
)
async def activate_activity_group(group_id: int, db: SessionDep) -> ActivityGroup:
    return await service.set_active(db, ActivityGroup, group_id, True)


@activity_groups.post(
    "/{group_id}/deactivate", response_model=ActivityGroupOut, dependencies=AdminOnly
)
async def deactivate_activity_group(group_id: int, db: SessionDep) -> ActivityGroup:
    return await service.set_active(db, ActivityGroup, group_id, False)


# ---------------------------------------------------------------- O&M projects

om_projects = APIRouter(prefix="/om-projects", tags=["dropdowns"])


@om_projects.get("", response_model=Page[OmProjectOut])
async def list_om_projects(params: Query_, user: CurrentUser, db: SessionDep) -> Page[OmProjectOut]:
    service.ensure_can_include_inactive(user, params.include_inactive)
    return await service.list_values(db, OmProject, OmProjectOut, params, params.include_inactive)


@om_projects.post("", response_model=OmProjectOut, status_code=201, dependencies=AdminOnly)
async def create_om_project(data: OmProjectCreate, db: SessionDep) -> OmProject:
    return await service.create_value(db, OmProject, data)


@om_projects.put("/order", status_code=204, dependencies=AdminOnly)
async def reorder_om_projects(data: ReorderIn, db: SessionDep) -> None:
    await service.reorder(db, OmProject, data.ids)


@om_projects.patch("/{om_project_id}", response_model=OmProjectOut, dependencies=AdminOnly)
async def update_om_project(om_project_id: int, data: OmProjectUpdate, db: SessionDep) -> OmProject:
    return await service.update_value(db, OmProject, om_project_id, data)


@om_projects.post("/{om_project_id}/activate", response_model=OmProjectOut, dependencies=AdminOnly)
async def activate_om_project(om_project_id: int, db: SessionDep) -> OmProject:
    return await service.set_active(db, OmProject, om_project_id, True)


@om_projects.post(
    "/{om_project_id}/deactivate", response_model=OmProjectOut, dependencies=AdminOnly
)
async def deactivate_om_project(om_project_id: int, db: SessionDep) -> OmProject:
    return await service.set_active(db, OmProject, om_project_id, False)


# ---------------------------------------------------------------- deviation reasons

deviation_reasons = APIRouter(prefix="/deviation-reasons", tags=["dropdowns"])


@deviation_reasons.get("", response_model=Page[DeviationReasonOut])
async def list_deviation_reasons(
    params: Query_, user: CurrentUser, db: SessionDep
) -> Page[DeviationReasonOut]:
    service.ensure_can_include_inactive(user, params.include_inactive)
    return await service.list_values(
        db, DeviationReason, DeviationReasonOut, params, params.include_inactive
    )


@deviation_reasons.post(
    "", response_model=DeviationReasonOut, status_code=201, dependencies=AdminOnly
)
async def create_deviation_reason(data: LongPlainLookupCreate, db: SessionDep) -> DeviationReason:
    return await service.create_value(db, DeviationReason, data)


@deviation_reasons.put("/order", status_code=204, dependencies=AdminOnly)
async def reorder_deviation_reasons(data: ReorderIn, db: SessionDep) -> None:
    await service.reorder(db, DeviationReason, data.ids)


@deviation_reasons.patch("/{reason_id}", response_model=DeviationReasonOut, dependencies=AdminOnly)
async def update_deviation_reason(
    reason_id: int, data: LongPlainLookupUpdate, db: SessionDep
) -> DeviationReason:
    return await service.update_value(db, DeviationReason, reason_id, data)


@deviation_reasons.post(
    "/{reason_id}/activate", response_model=DeviationReasonOut, dependencies=AdminOnly
)
async def activate_deviation_reason(reason_id: int, db: SessionDep) -> DeviationReason:
    return await service.set_active(db, DeviationReason, reason_id, True)


@deviation_reasons.post(
    "/{reason_id}/deactivate", response_model=DeviationReasonOut, dependencies=AdminOnly
)
async def deactivate_deviation_reason(reason_id: int, db: SessionDep) -> DeviationReason:
    return await service.set_active(db, DeviationReason, reason_id, False)
