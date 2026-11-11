from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Identity, String, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import RunStatus, str_enum


class Process(TimestampMixin, Base):
    """A user's reusable checklist template. Deletable only while it has no runs."""

    __tablename__ = "processes"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=true())


class ProcessStep(Base):
    __tablename__ = "process_steps"
    __table_args__ = (CheckConstraint("estimated_hours > 0", name="estimated_hours_positive"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # Steps go with their process (which can only be deleted when it has no runs).
    process_id: Mapped[int] = mapped_column(
        ForeignKey("processes.id", ondelete="CASCADE"), index=True
    )
    step_order: Mapped[int]
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    default_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    estimated_hours: Mapped[Decimal | None]


class ProcessRun(Base):
    """Not deletable (cancel instead). RESTRICT also blocks deleting a process with runs."""

    __tablename__ = "process_runs"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("processes.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[RunStatus] = mapped_column(
        str_enum(RunStatus, "status"), server_default=RunStatus.IN_PROGRESS.value
    )
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]
