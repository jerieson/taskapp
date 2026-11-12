"""Sessions, password login and password changes."""

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    burn_password_check,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.base import utcnow
from app.models import User, UserSession

logger = logging.getLogger("app.auth")


@dataclass(frozen=True)
class NewSession:
    """A freshly created session. The plain tokens exist only here (for the cookies)."""

    user: User
    session: UserSession
    token: str
    csrf_token: str


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession


async def check_password(password: str, password_hash: str | None) -> bool:
    """Argon2 is deliberately slow, so it runs off the event loop."""
    if password_hash is None:
        await run_in_threadpool(burn_password_check, password)
        return False
    return await run_in_threadpool(verify_password, password, password_hash)


async def make_password_hash(password: str) -> str:
    return await run_in_threadpool(hash_password, password)


async def create_session(db: AsyncSession, user: User, settings: Settings) -> NewSession:
    """Create a session for `user` and commit."""
    token = generate_token()
    csrf_token = generate_token()
    row = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=csrf_token,
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(row)
    await db.commit()
    return NewSession(user=user, session=row, token=token, csrf_token=csrf_token)


async def get_auth_context(db: AsyncSession, token: str | None) -> AuthContext | None:
    """The live session for a cookie token: not revoked, not expired, user active."""
    if not token:
        return None
    row = (
        await db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(
                UserSession.token_hash == hash_token(token),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > utcnow(),
                User.is_active.is_(True),
            )
        )
    ).one_or_none()
    if row is None:
        return None
    return AuthContext(user=row.User, session=row.UserSession)


async def revoke_session(db: AsyncSession, session: UserSession) -> None:
    session.revoked_at = utcnow()
    await db.commit()


async def revoke_user_sessions(
    db: AsyncSession, user_id: int, *, except_session_id: int | None = None
) -> None:
    """Revoke every live session of a user (optionally keeping one). Does not commit."""
    stmt = update(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if except_session_id is not None:
        stmt = stmt.where(UserSession.id != except_session_id)
    await db.execute(stmt.values(revoked_at=utcnow()))


async def login(
    db: AsyncSession, username: str, password: str, settings: Settings
) -> NewSession | None:
    """Check the credentials and create a session; None if they are invalid.

    Unknown, inactive and Google-only users all fail the same way, in the same time.
    """
    user = await db.scalar(select(User).where(User.username == username))
    valid = await check_password(password, user.password_hash if user else None)
    if user is None or not valid or not user.is_active:
        logger.info(
            "login_failed",
            extra={"fields": {"user_id": user.id if user else None}},
        )
        return None
    logger.info("login_succeeded", extra={"fields": {"user_id": user.id}})
    return await create_session(db, user, settings)


async def change_password(
    db: AsyncSession, ctx: AuthContext, current_password: str, new_password: str
) -> None:
    """Set a new password (current one required) and revoke all other sessions."""
    user = ctx.user
    if user.password_hash is None:
        raise AppError(
            400,
            "password_not_set",
            "This account signs in with Google and has no password. "
            "Ask an admin for a password reset link to set one.",
        )
    if not await check_password(current_password, user.password_hash):
        raise AppError(
            400,
            "invalid_current_password",
            "Current password is incorrect",
            fields={"current_password": "Current password is incorrect"},
        )
    user.password_hash = await make_password_hash(new_password)
    await revoke_user_sessions(db, user.id, except_session_id=ctx.session.id)
    await db.commit()
    logger.info("password_changed", extra={"fields": {"user_id": user.id}})
