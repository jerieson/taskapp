"""Factory helpers for tests. Each creates a valid row (plus any required parents),
flushes it so it has an id, and returns it. Keyword arguments override any column.

Labels and names are generated and unique; tests never depend on seed labels.
"""

import itertools
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.base import Base
from app.models import Category, Priority, ProdLog, Project, Role, Status, Task, Team, User

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


async def make_log(
    session: AsyncSession, *, user: User | None = None, task: Task | None = None, **kw: Any
) -> ProdLog:
    """team_id is snapshotted from the author and updated_by defaults to the author."""
    if user is None:
        user = await make_user(session)
    fields: dict[str, Any] = {
        "user_id": user.id,
        "team_id": user.team_id,
        "updated_by": user.id,
        "task_id": task.id if task else None,
        "log_date": date.today(),
        "title": f"Log {_n()}",
        "hours_spent": Decimal("1.00"),
    }
    if "category_id" not in kw:
        from_task = task.category_id if task else None
        fields["category_id"] = from_task or (await make_category(session)).id
    return await _save(session, ProdLog(**{**fields, **kw}))
