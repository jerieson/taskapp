from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin
from app.models.enums import Role, str_enum


class UserSession(CreatedAtMixin, Base):
    """Server-side login session. Only the hash of the cookie token is stored."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]


class Invite(CreatedAtMixin, Base):
    __tablename__ = "invites"
    __table_args__ = (CheckConstraint("role <> 'admin'", name="role_not_admin"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"))
    # Invites are not history worth keeping once their team is gone.
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


class PasswordReset(CreatedAtMixin, Base):
    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
