from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Identity, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        # A task copied from a process step always belongs to that step's run.
        CheckConstraint(
            "process_step_id IS NULL OR process_run_id IS NOT NULL", name="step_requires_run"
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    status_id: Mapped[int] = mapped_column(
        ForeignKey("statuses.id", ondelete="RESTRICT"), index=True
    )
    priority_id: Mapped[int] = mapped_column(
        ForeignKey("priorities.id", ondelete="RESTRICT"), index=True
    )
    due_date: Mapped[date | None]
    completed_at: Mapped[datetime | None]
    process_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("process_runs.id", ondelete="RESTRICT"), index=True
    )
    process_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("process_steps.id", ondelete="SET NULL"), index=True
    )
