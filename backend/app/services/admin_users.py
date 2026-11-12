"""User management (admin only). Users are never deleted, only deactivated."""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.pagination import Page
from app.models import Role, Team, User
from app.schemas.auth import TeamRef
from app.schemas.users import AdminUserOut, AdminUserQuery, AdminUserUpdate
from app.services.auth import revoke_user_sessions

logger = logging.getLogger("app.admin_users")


def _out(user: User, team: Team | None) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        team=TeamRef.model_validate(team) if team else None,
        is_active=user.is_active,
        has_password=user.password_hash is not None,
        google_linked=user.google_sub is not None,
        created_at=user.created_at,
    )


async def _get(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise AppError(404, "not_found", "User not found")
    return user


async def _to_out(db: AsyncSession, user: User) -> AdminUserOut:
    team = await db.get(Team, user.team_id) if user.team_id is not None else None
    return _out(user, team)


async def list_users(db: AsyncSession, params: AdminUserQuery) -> Page[AdminUserOut]:
    stmt = select(User, Team).outerjoin(Team, Team.id == User.team_id)
    if params.team_id is not None:
        stmt = stmt.where(User.team_id == params.team_id)
    if params.role is not None:
        stmt = stmt.where(User.role == params.role)
    if params.is_active is not None:
        stmt = stmt.where(User.is_active.is_(params.is_active))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.execute(
        stmt.order_by(User.is_active.desc(), User.username)
        .limit(params.limit)
        .offset(params.offset)
    )
    return Page[AdminUserOut].build([_out(u, t) for u, t in rows.all()], total, params)


async def update_user(
    db: AsyncSession, admin: User, user_id: int, data: AdminUserUpdate
) -> AdminUserOut:
    """Change role and/or team, keeping `admin <=> no team` true."""
    user = await _get(db, user_id)
    sent = data.model_fields_set
    new_role = data.role if data.role is not None else user.role

    if user.id == admin.id and new_role != Role.ADMIN:
        raise AppError(
            409,
            "self_demotion",
            "You cannot change your own role",
            fields={"role": "You cannot change your own role"},
        )

    if new_role == Role.ADMIN:
        if "team_id" in sent and data.team_id is not None:
            raise AppError(
                422,
                "validation_error",
                "Admins cannot belong to a team",
                fields={"team_id": "Admins cannot belong to a team"},
            )
        new_team_id = None
    else:
        new_team_id = data.team_id if "team_id" in sent else user.team_id
        if new_team_id is None:
            raise AppError(
                422,
                "validation_error",
                "Managers and devs must belong to a team",
                fields={"team_id": "Choose a team"},
            )
        if await db.get(Team, new_team_id) is None:
            raise AppError(
                422, "validation_error", "Team does not exist", fields={"team_id": "Team not found"}
            )

    user.role = new_role
    user.team_id = new_team_id
    await db.commit()
    await db.refresh(user)
    logger.info(
        "user_updated",
        extra={"fields": {"user_id": user.id, "role": str(user.role), "team_id": user.team_id}},
    )
    return await _to_out(db, user)


async def set_active(db: AsyncSession, admin: User, user_id: int, active: bool) -> AdminUserOut:
    """Activate or deactivate. Deactivation revokes every session immediately."""
    user = await _get(db, user_id)
    if not active and user.id == admin.id:
        raise AppError(409, "self_deactivation", "You cannot deactivate your own account")
    user.is_active = active
    if not active:
        await revoke_user_sessions(db, user.id)
    await db.commit()
    await db.refresh(user)
    logger.info(
        "user_activated" if active else "user_deactivated", extra={"fields": {"user_id": user.id}}
    )
    return await _to_out(db, user)
