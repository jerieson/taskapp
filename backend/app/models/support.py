from sqlalchemy import ForeignKey, Identity, Index, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SupportEntry(TimestampMixin, Base):
    """A shared support dictionary entry: a known concern, its cause and resolution.

    Everyone reads every entry; the author or an admin edits or deactivates it.
    Entries are never deleted.
    """

    __tablename__ = "support_entries"
    __table_args__ = (Index(None, "is_active", "created_at"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    type_id: Mapped[int] = mapped_column(
        ForeignKey("support_types.id", ondelete="RESTRICT"), index=True
    )
    # Free text (with suggestions from existing entries), not a dropdown.
    project: Mapped[str | None] = mapped_column(String(100))
    module: Mapped[str | None] = mapped_column(String(100))
    sub_module: Mapped[str | None] = mapped_column(String(100))
    concern: Mapped[str] = mapped_column(Text)
    cause: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)
    query: Mapped[str | None] = mapped_column(Text)
    """SQL, shown as code."""
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
