from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Identity, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class DailyPlan(CreatedAtMixin, Base):
    __tablename__ = "daily_plans"
    # Also the (user_id, plan_date) lookup index.
    __table_args__ = (UniqueConstraint("user_id", "plan_date"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    plan_date: Mapped[date]
    ai_generated: Mapped[bool] = mapped_column(server_default=false())


class DailyPlanItem(Base):
    __tablename__ = "daily_plan_items"
    __table_args__ = (
        UniqueConstraint("daily_plan_id", "task_id"),
        CheckConstraint(
            "suggested_hours > 0 AND suggested_hours <= 24", name="suggested_hours_range"
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    daily_plan_id: Mapped[int] = mapped_column(ForeignKey("daily_plans.id", ondelete="CASCADE"))
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    item_order: Mapped[int]
    suggested_hours: Mapped[Decimal | None]
    ai_reason: Mapped[str | None] = mapped_column(Text)
