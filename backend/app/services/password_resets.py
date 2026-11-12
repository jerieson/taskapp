"""Admin-generated password reset links (no email service: the admin sends the link)."""

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import generate_token, hash_token
from app.db.base import utcnow
from app.models import PasswordReset, User
from app.schemas.password_resets import PasswordResetCheck, PasswordResetCreated
from app.services.auth import make_password_hash, revoke_user_sessions

logger = logging.getLogger("app.password_resets")


async def create_reset(
    db: AsyncSession, admin: User, user_id: int, settings: Settings
) -> PasswordResetCreated:
    user = await db.get(User, user_id)
    if user is None:
        raise AppError(404, "not_found", "User not found")
    if not user.is_active:
        raise AppError(409, "user_inactive", "Reactivate the user before resetting their password")

    token = generate_token()
    reset = PasswordReset(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(hours=settings.reset_ttl_hours),
        created_by=admin.id,
    )
    db.add(reset)
    await db.commit()
    logger.info(
        "password_reset_created", extra={"fields": {"reset_id": reset.id, "user_id": user.id}}
    )
    return PasswordResetCreated(
        reset_url=f"{settings.frontend_url}/reset-password/{token}", expires_at=reset.expires_at
    )


async def _find_usable(
    db: AsyncSession, token: str, *, lock: bool = False
) -> tuple[PasswordReset, User] | None:
    """An unused, unexpired reset whose user is still active."""
    stmt = (
        select(PasswordReset, User)
        .join(User, User.id == PasswordReset.user_id)
        .where(
            PasswordReset.token_hash == hash_token(token),
            PasswordReset.used_at.is_(None),
            PasswordReset.expires_at > utcnow(),
            User.is_active.is_(True),
        )
    )
    if lock:
        stmt = stmt.with_for_update(of=PasswordReset)
    row = (await db.execute(stmt)).one_or_none()
    return (row.PasswordReset, row.User) if row else None


async def check_reset(db: AsyncSession, token: str) -> PasswordResetCheck:
    found = await _find_usable(db, token)
    if found is None:
        return PasswordResetCheck(valid=False)
    reset, user = found
    return PasswordResetCheck(valid=True, username=user.username, expires_at=reset.expires_at)


async def use_reset(db: AsyncSession, token: str, new_password: str) -> None:
    """Set the new password, mark the link used and revoke all the user's sessions."""
    found = await _find_usable(db, token, lock=True)
    if found is None:
        raise AppError(404, "reset_invalid", "This password reset link is invalid, used or expired")
    reset, user = found
    user.password_hash = await make_password_hash(new_password)
    reset.used_at = utcnow()
    await revoke_user_sessions(db, user.id)
    await db.commit()
    logger.info("password_reset_used", extra={"fields": {"reset_id": reset.id, "user_id": user.id}})
