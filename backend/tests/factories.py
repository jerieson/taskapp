"""Factory helpers for tests. Each creates a valid row (plus any required parents),
flushes it so it has an id, and returns it. Keyword arguments override any column.

Labels and names are generated and unique; tests never depend on seed labels.
"""

import itertools
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.base import Base
from app.models import (
    Activity,
    ActivityGroup,
    ActivityGroupMember,
    Category,
    DeviationReason,
    OmProject,
    Priority,
    ProdLog,
    Project,
    Role,
    Status,
    Task,
    Team,
    User,
    WorkSetup,
)

_seq = itertools.count(1)

# Unusable placeholder (not a valid argon2 hash) for users who don't need to log in.
NO_PASSWORD = "!unusable"


def _n() -> int:
    return next(_seq)


async def _save[M: Base](session: AsyncSession, obj: M) -> M:
    session.add(obj)
    await session.flush()
    return obj


async def make_team(session: AsyncSession, **kw: Any) -> Team:
    return await _save(session, Team(**{"name": f"Team {_n()}", **kw}))


async def make_user(
    session: AsyncSession,
    *,
    role: Role = Role.DEV,
    team: Team | None = None,
    password: str | None = None,
    **kw: Any,
) -> User:
    """Non-admin users get a new team unless `team` or `team_id` is given."""
    n = _n()
    if role != Role.ADMIN and team is None and "team_id" not in kw:
        team = await make_team(session)
    fields: dict[str, Any] = {
        "username": f"user{n}",
        "email": f"user{n}@example.com",
        "password_hash": hash_password(password) if password else NO_PASSWORD,
        "role": role,
        "team_id": team.id if team else None,
    }
    return await _save(session, User(**{**fields, **kw}))


async def make_category(session: AsyncSession, **kw: Any) -> Category:
    return await _save(session, Category(**{"label": f"Category {_n()}", **kw}))


async def make_status(session: AsyncSession, **kw: Any) -> Status:
    return await _save(session, Status(**{"label": f"Status {_n()}", **kw}))


async def make_priority(session: AsyncSession, **kw: Any) -> Priority:
    return await _save(session, Priority(**{"label": f"Priority {_n()}", **kw}))


async def make_project(session: AsyncSession, **kw: Any) -> Project:
    return await _save(session, Project(**{"name": f"Project {_n()}", **kw}))


async def make_work_setup(session: AsyncSession, **kw: Any) -> WorkSetup:
    """The migration seeds a default work set-up; new ones are not the default."""
    return await _save(session, WorkSetup(**{"label": f"Work set-up {_n()}", **kw}))


async def make_activity(session: AsyncSession, **kw: Any) -> Activity:
    return await _save(session, Activity(**{"label": f"Activity {_n()}", **kw}))


async def make_om_project(session: AsyncSession, **kw: Any) -> OmProject:
    return await _save(session, OmProject(**{"label": f"OM project {_n()}", **kw}))


async def make_deviation_reason(session: AsyncSession, **kw: Any) -> DeviationReason:
    return await _save(session, DeviationReason(**{"label": f"Reason {_n()}", **kw}))


async def make_activity_group(
    session: AsyncSession, *, activities: Sequence[Activity] = (), **kw: Any
) -> ActivityGroup:
    """`activities` become the group's members, in order."""
    members = [
        ActivityGroupMember(activity_id=a.id, sort_order=i) for i, a in enumerate(activities, 1)
    ]
    group = ActivityGroup(**{"label": f"Group {_n()}", **kw})
    group.members = members
    return await _save(session, group)


async def make_task(session: AsyncSession, *, user: User | None = None, **kw: Any) -> Task:
    if user is None and "user_id" not in kw:
        user = await make_user(session)
    fields: dict[str, Any] = {"title": f"Task {_n()}"}
    if user is not None:
        fields["user_id"] = user.id
    if "status_id" not in kw:
        fields["status_id"] = (await make_status(session)).id
    if "priority_id" not in kw:
        fields["priority_id"] = (await make_priority(session)).id
    return await _save(session, Task(**{**fields, **kw}))


async def make_log(session: AsyncSession, *, user: User | None = None, **kw: Any) -> ProdLog:
    """team_id is snapshotted from the author and updated_by defaults to the author.

    Defaults: actual hours 1 (no planned hours), a new activity, the seeded default
    work set-up. Link rules are not applied (the service checks those)."""
    if user is None:
        user = await make_user(session)
    fields: dict[str, Any] = {
        "user_id": user.id,
        "team_id": user.team_id,
        "updated_by": user.id,
        "log_date": date.today(),
        "description": f"Log {_n()}",
        "hours_spent": Decimal("1.00"),
    }
    if "work_setup_id" not in kw:
        fields["work_setup_id"] = await session.scalar(
            select(WorkSetup.id).where(WorkSetup.is_default)
        )
    if "activity_id" not in kw:
        fields["activity_id"] = (await make_activity(session)).id
    if "category_id" not in kw:
        fields["category_id"] = (await make_category(session)).id
    return await _save(session, ProdLog(**{**fields, **kw}))


class LinkedRefs:
    """A category, a project under it, and an activity in the project's group: values
    that pass the prod log linked-dropdown rules."""

    def __init__(
        self, category: Category, project: Project, group: ActivityGroup, activity: Activity
    ) -> None:
        self.category, self.project, self.group, self.activity = category, project, group, activity

    def ids(self) -> dict[str, int]:
        return {
            "category_id": self.category.id,
            "project_id": self.project.id,
            "activity_id": self.activity.id,
        }


async def make_linked(session: AsyncSession, **category_kw: Any) -> LinkedRefs:
    category = await make_category(session, **category_kw)
    activity = await make_activity(session)
    group = await make_activity_group(session, activities=[activity])
    project = await make_project(session, categories=[category], activity_group_id=group.id)
    return LinkedRefs(category, project, group, activity)
