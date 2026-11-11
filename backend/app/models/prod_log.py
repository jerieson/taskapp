from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Identity, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ProdLog(TimestampMixin, Base):
    """A daily productivity log entry.

    team_id is a snapshot of the author's team at creation and never changes;
    manager access and team dashboards filter on it.
    """

    __tablename__ = "prod_logs"
    __table_args__ = (
        CheckConstraint("hours_spent > 0 AND hours_spent <= 24", name="hours_spent_range"),
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
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    hours_spent: Mapped[Decimal]
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
