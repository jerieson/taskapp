"""Admin-managed dropdown values. Rows are deactivated, never deleted.

Code never refers to a row by its label; it uses the is_default / is_done flags.
"""

from sqlalchemy import CheckConstraint, Identity, Index, String, Text, false, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin

_COLOR_CHECK = "color ~ '^#[0-9A-Fa-f]{6}$'"


class _LookupMixin:
    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    label: Mapped[str] = mapped_column(String(50), unique=True)
    color: Mapped[str | None] = mapped_column(String(7))
    sort_order: Mapped[int] = mapped_column(server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(server_default=true())


def _single_default_args(table: str) -> tuple[CheckConstraint | Index, ...]:
    return (
        CheckConstraint(_COLOR_CHECK, name="color_hex"),
        # The default row must be active ...
        CheckConstraint("is_active OR NOT is_default", name="default_is_active"),
        # ... and at most one row can be the default.
        Index(
            f"uq_{table}_single_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )


class Category(_LookupMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (CheckConstraint(_COLOR_CHECK, name="color_hex"),)


class Status(_LookupMixin, Base):
    __tablename__ = "statuses"
    __table_args__ = _single_default_args("statuses")

    is_default: Mapped[bool] = mapped_column(server_default=false())
    is_done: Mapped[bool] = mapped_column(server_default=false())


class Priority(_LookupMixin, Base):
    __tablename__ = "priorities"
    __table_args__ = _single_default_args("priorities")

    is_default: Mapped[bool] = mapped_column(server_default=false())


class Project(CreatedAtMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, server_default="")
    is_active: Mapped[bool] = mapped_column(server_default=true())
