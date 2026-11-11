from sqlalchemy import CheckConstraint, ForeignKey, Identity, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import Role, str_enum


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Admins have no team; every other user belongs to exactly one team.
        CheckConstraint(
            "(role = 'admin' AND team_id IS NULL) OR (role <> 'admin' AND team_id IS NOT NULL)",
            name="team_matches_role",
        ),
        # A user must be able to log in somehow.
        CheckConstraint(
            "password_hash IS NOT NULL OR google_sub IS NOT NULL",
            name="has_login_method",
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"))
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), index=True
    )
    is_active: Mapped[bool] = mapped_column(server_default=true())
