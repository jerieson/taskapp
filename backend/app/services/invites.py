"""Invites: admin creates them, the invitee accepts with a password or with Google."""

import logging
from datetime import timedelta

from sqlalchemy import ColumnElement, and_, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.pagination import Page, PaginationParams, paginate
from app.core.security import generate_token, hash_token
from app.db.base import utcnow
from app.models import Invite, Team, User
from app.schemas.invites import (
    InviteAcceptIn,
    InviteCreate,
    InviteCreated,
    InviteOut,
    InvitePublicOut,
    InviteStatus,
)
from app.services.auth import NewSession, create_session, make_password_hash

logger = logging.getLogger("app.invites")


def invalid_invite() -> AppError:
    return AppError(404, "invite_invalid", "This invite link is invalid or has expired")


def invite_status(invite: Invite) -> InviteStatus:
    if invite.accepted_at is not None:
        return InviteStatus.ACCEPTED
    if invite.expires_at <= utcnow():
        return InviteStatus.EXPIRED
    return InviteStatus.PENDING


def _to_out(invite: Invite) -> InviteOut:
    return InviteOut(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        team_id=invite.team_id,
        status=invite_status(invite),
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        created_by=invite.created_by,
        created_at=invite.created_at,
    )


def _is_pending() -> ColumnElement[bool]:
    return and_(Invite.accepted_at.is_(None), Invite.expires_at > utcnow())


async def email_has_user(db: AsyncSession, email: str) -> bool:
    return bool(await db.scalar(select(exists().where(func.lower(User.email) == email))))


async def find_pending_invite_by_email(db: AsyncSession, email: str) -> Invite | None:
    return await db.scalar(
        select(Invite)
        .where(func.lower(Invite.email) == email.lower(), _is_pending())
        .order_by(Invite.created_at.desc())
        .limit(1)
        .with_for_update()
    )


async def find_pending_invite_by_token(db: AsyncSession, token: str | None) -> Invite | None:
    """The pending invite for a link token, locked for the rest of the transaction."""
    if not token:
        return None
    return await db.scalar(
        select(Invite)
        .where(Invite.token_hash == hash_token(token), _is_pending())
        .with_for_update()
    )


async def create_invite(
    db: AsyncSession, admin: User, data: InviteCreate, settings: Settings
) -> InviteCreated:
    if await db.get(Team, data.team_id) is None:
        raise AppError(
            422, "validation_error", "Team does not exist", fields={"team_id": "Team not found"}
        )
    if await email_has_user(db, data.email):
        raise AppError(
            409,
            "email_taken",
            "A user with this email already exists",
            fields={"email": "A user with this email already exists"},
        )
    if await find_pending_invite_by_email(db, data.email) is not None:
        raise AppError(
            409,
            "invite_pending",
            "A pending invite for this email already exists",
            fields={"email": "A pending invite for this email already exists"},
        )

    token = generate_token()
    invite = Invite(
        email=data.email,
        role=data.role,
        team_id=data.team_id,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(hours=settings.invite_ttl_hours),
        created_by=admin.id,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    logger.info("invite_created", extra={"fields": {"invite_id": invite.id}})
    return InviteCreated.model_validate(
        {
            **_to_out(invite).model_dump(),
            "invite_url": f"{settings.frontend_url}/invite/{token}",
        }
    )


async def list_invites(db: AsyncSession, params: PaginationParams) -> Page[InviteOut]:
    stmt = select(Invite).order_by(Invite.created_at.desc(), Invite.id.desc())
    items, total = await paginate(db, stmt, params)
    return Page[InviteOut].build([_to_out(i) for i in items], total, params)


async def delete_invite(db: AsyncSession, invite_id: int) -> None:
    """Revoke an invite that has not been accepted (accepted invites are history)."""
    invite = await db.get(Invite, invite_id)
    if invite is None:
        raise AppError(404, "not_found", "Invite not found")
    if invite.accepted_at is not None:
        raise AppError(409, "invite_accepted", "An accepted invite cannot be revoked")
    await db.delete(invite)
    await db.commit()
    logger.info("invite_revoked", extra={"fields": {"invite_id": invite_id}})


async def get_public_invite(db: AsyncSession, token: str) -> InvitePublicOut:
    row = (
        await db.execute(
            select(Invite, Team.name)
            .join(Team, Team.id == Invite.team_id)
            .where(Invite.token_hash == hash_token(token), _is_pending())
        )
    ).one_or_none()
    if row is None:
        raise invalid_invite()
    invite, team_name = row
    return InvitePublicOut(
        email=invite.email, role=invite.role, team_name=team_name, expires_at=invite.expires_at
    )


async def create_user_from_invite(
    db: AsyncSession,
    invite: Invite,
    *,
    username: str,
    password_hash: str | None = None,
    google_sub: str | None = None,
) -> User:
    """Create the invited user, mark the invite accepted and flush (no commit).

    The caller must hold the invite row lock (see find_pending_invite_*).
    """
    if await email_has_user(db, invite.email):
        raise AppError(409, "email_taken", "A user with this email already exists")
    user = User(
        username=username,
        email=invite.email.lower(),
        password_hash=password_hash,
        google_sub=google_sub,
        role=invite.role,
        team_id=invite.team_id,
    )
    db.add(user)
    invite.accepted_at = utcnow()
    try:
        await db.flush()
    except IntegrityError as exc:  # lost a race on username/email
        await db.rollback()
        raise AppError(409, "account_conflict", "This account already exists") from exc
    logger.info(
        "invite_accepted",
        extra={"fields": {"invite_id": invite.id, "user_id": user.id}},
    )
    return user


async def accept_invite(
    db: AsyncSession, token: str, data: InviteAcceptIn, settings: Settings
) -> NewSession:
    """Accept with username + password and log the new user in."""
    invite = await find_pending_invite_by_token(db, token)
    if invite is None:
        raise invalid_invite()
    if await db.scalar(select(exists().where(User.username == data.username))):
        raise AppError(
            409,
            "username_taken",
            "This username is already taken",
            fields={"username": "This username is already taken"},
        )
    user = await create_user_from_invite(
        db, invite, username=data.username, password_hash=await make_password_hash(data.password)
    )
    return await create_session(db, user, settings)
