from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Identity, Index, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ProdLog(TimestampMixin, Base):
    """A row of the productivity log: planned hours ahead of time, actual hours after.

    team_id is a snapshot of the author's team at creation and never changes;
    manager access and team dashboards filter on it.
    """

    __tablename__ = "prod_logs"
    __table_args__ = (
        CheckConstraint("hours_spent > 0 AND hours_spent <= 24", name="hours_spent_range"),
        CheckConstraint("planned_hours > 0 AND planned_hours <= 24", name="planned_hours_range"),
        CheckConstraint("planned_hours IS NOT NULL OR hours_spent IS NOT NULL", name="has_hours"),
        # These also serve as the indexes for the user_id and team_id foreign keys.
        Index(None, "user_id", "log_date"),
        Index(None, "team_id", "log_date"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"))
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    log_date: Mapped[date]
    work_setup_id: Mapped[int] = mapped_column(
        ForeignKey("work_setups.id", ondelete="RESTRICT"), index=True
    )
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="RESTRICT"), index=True
    )
    # A short note; "Remarks" in the sheet is `description`.
    title: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    # Nullable for old rows; the service requires it on new rows.
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    om_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("om_projects.id", ondelete="RESTRICT"), index=True
    )
    is_planned: Mapped[bool] = mapped_column(server_default=true())
    planned_hours: Mapped[Decimal | None]
    # "Actual Hours Consumed".
    hours_spent: Mapped[Decimal | None]
    # "Reason for Deviation (if any)".
    deviation_reason_id: Mapped[int | None] = mapped_column(
        ForeignKey("deviation_reasons.id", ondelete="RESTRICT"), index=True
    )
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
