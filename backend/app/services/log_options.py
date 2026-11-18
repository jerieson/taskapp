"""Everything the prod log form needs to fill its linked dropdowns, in one response.

Only active values are returned, and links to inactive values are dropped (an inactive
group gives its projects no group; inactive categories and activities are left out of
the id lists). Values already on an existing log are shown from the log itself.
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Activity,
    ActivityGroup,
    Category,
    DeviationReason,
    OmProject,
    Project,
    WorkSetup,
)
from app.schemas.lookups import (
    ActivityOut,
    CategoryOut,
    DeviationReasonOut,
    LogOptionGroup,
    LogOptionProject,
    LogOptionsOut,
    OmProjectOut,
    WorkSetupOut,
)


async def get_log_options(db: AsyncSession, workday_hours: Decimal) -> LogOptionsOut:
    categories = (
        await db.scalars(
            select(Category).where(Category.is_active).order_by(Category.sort_order, Category.id)
        )
    ).all()
    activities = (
        await db.scalars(
            select(Activity).where(Activity.is_active).order_by(Activity.sort_order, Activity.id)
        )
    ).all()
    groups = (
        await db.scalars(
            select(ActivityGroup)
            .where(ActivityGroup.is_active)
            .order_by(ActivityGroup.sort_order, ActivityGroup.id)
        )
    ).all()
    projects = (
        await db.scalars(
            select(Project).where(Project.is_active).order_by(func.lower(Project.name), Project.id)
        )
    ).all()
    om_projects = await db.scalars(
        select(OmProject).where(OmProject.is_active).order_by(OmProject.sort_order, OmProject.id)
    )
    work_setups = await db.scalars(
        select(WorkSetup).where(WorkSetup.is_active).order_by(WorkSetup.sort_order, WorkSetup.id)
    )
    deviation_reasons = await db.scalars(
        select(DeviationReason)
        .where(DeviationReason.is_active)
        .order_by(DeviationReason.sort_order, DeviationReason.id)
    )

    active_categories = {category.id for category in categories}
    active_activities = {activity.id for activity in activities}
    active_groups = {group.id for group in groups}
    return LogOptionsOut(
        workday_hours=workday_hours,
        categories=[CategoryOut.model_validate(c) for c in categories],
        projects=[
            LogOptionProject(
                id=project.id,
                name=project.name,
                category_ids=[i for i in project.category_ids if i in active_categories],
                activity_group_id=(
                    project.activity_group_id
                    if project.activity_group_id in active_groups
                    else None
                ),
            )
            for project in projects
        ],
        activity_groups=[
            LogOptionGroup(
                id=group.id,
                label=group.label,
                activity_ids=[i for i in group.activity_ids if i in active_activities],
            )
            for group in groups
        ],
        activities=[ActivityOut.model_validate(a) for a in activities],
        om_projects=[OmProjectOut.model_validate(o) for o in om_projects],
        work_setups=[WorkSetupOut.model_validate(w) for w in work_setups],
        deviation_reasons=[DeviationReasonOut.model_validate(d) for d in deviation_reasons],
    )
