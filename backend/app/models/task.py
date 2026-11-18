from datetime import date, datetime

from sqlalchemy import ForeignKey, Identity, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
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
