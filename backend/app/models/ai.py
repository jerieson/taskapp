from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, Identity, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin
from app.models.enums import AIFeature, str_enum


class AISummary(CreatedAtMixin, Base):
    """Cached AI team summary for a team + period."""

    __tablename__ = "ai_summaries"
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="period_order"),
        # Cache lookup; also the team_id foreign key index.
        Index(None, "team_id", "period_start", "period_end"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    # A cached summary is not worth blocking a team deletion for.
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    period_start: Mapped[date]
    period_end: Mapped[date]
    summary_text: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))


class AIRequest(CreatedAtMixin, Base):
    """One row per LLM call (success or failure); drives usage stats and daily limits."""

    __tablename__ = "ai_requests"
    __table_args__ = (
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="tokens_non_negative"),
        # Daily-limit count; also the user_id foreign key index.
        Index(None, "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    feature: Mapped[AIFeature] = mapped_column(str_enum(AIFeature, "feature"))
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(server_default=text("0"))
    success: Mapped[bool]
