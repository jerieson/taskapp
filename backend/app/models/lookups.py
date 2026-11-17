"""Admin-managed dropdown values and projects. Rows are deactivated, never deleted.

Code never refers to a row by its label; it uses the is_default / is_done flags.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Identity,
    Index,
    String,
    Table,
    Text,
    false,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin

_COLOR_CHECK = "color ~ '^#[0-9A-Fa-f]{6}$'"


class _PlainLookupMixin:
    """A dropdown value without a color."""

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    label: Mapped[str] = mapped_column(String(50), unique=True)
    sort_order: Mapped[int] = mapped_column(server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(server_default=true())


class _LookupMixin(_PlainLookupMixin):
    color: Mapped[str | None] = mapped_column(String(7))


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

    # Log rows in this category offer "Project (For O&M)".
    requires_om_project: Mapped[bool] = mapped_column(server_default=false())


class Status(_LookupMixin, Base):
    __tablename__ = "statuses"
    __table_args__ = _single_default_args("statuses")

    is_default: Mapped[bool] = mapped_column(server_default=false())
    is_done: Mapped[bool] = mapped_column(server_default=false())


class Priority(_LookupMixin, Base):
    __tablename__ = "priorities"
    __table_args__ = _single_default_args("priorities")

    is_default: Mapped[bool] = mapped_column(server_default=false())


class WorkSetup(_LookupMixin, Base):
    """Remote, On-Site, ... New log rows get the default."""

    __tablename__ = "work_setups"
    __table_args__ = _single_default_args("work_setups")

    is_default: Mapped[bool] = mapped_column(server_default=false())


class Activity(_LookupMixin, Base):
    """What a log row was spent on ("Testing: UAT"). Listed in one or more groups."""

    __tablename__ = "activities"
    __table_args__ = (CheckConstraint(_COLOR_CHECK, name="color_hex"),)

    label: Mapped[str] = mapped_column(String(100), unique=True)


class OmProject(_PlainLookupMixin, Base):
    """Values of "Project (For O&M)"."""

    __tablename__ = "om_projects"

    label: Mapped[str] = mapped_column(String(100), unique=True)


class ActivityGroupMember(Base):
    __tablename__ = "activity_group_members"

    activity_group_id: Mapped[int] = mapped_column(
        ForeignKey("activity_groups.id"), primary_key=True
    )
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id"), primary_key=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(server_default=text("0"))


class ActivityGroup(_PlainLookupMixin, Base):
    """An ordered list of activities; a project's group decides which activities it offers."""

    __tablename__ = "activity_groups"

    members: Mapped[list[ActivityGroupMember]] = relationship(
        lazy="selectin",
        order_by=(ActivityGroupMember.sort_order, ActivityGroupMember.activity_id),
        cascade="all, delete-orphan",
    )

    @property
    def activity_ids(self) -> list[int]:
        return [member.activity_id for member in self.members]


project_categories = Table(
    "project_categories",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id"), primary_key=True),
    Column("category_id", ForeignKey("categories.id"), primary_key=True, index=True),
)


class Project(CreatedAtMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, server_default="")
    is_active: Mapped[bool] = mapped_column(server_default=true())
    # Which activities can be logged against this project.
    activity_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("activity_groups.id"), index=True
    )

    categories: Mapped[list[Category]] = relationship(
        secondary=project_categories, lazy="selectin", order_by=Category.sort_order
    )

    @property
    def category_ids(self) -> list[int]:
        return [category.id for category in self.categories]
