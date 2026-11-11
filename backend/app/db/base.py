from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, Numeric, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names so Alembic migrations are stable.
# Explicit names on CHECK constraints become ck_<table>_<name>; indexes and unique
# constraints without an explicit name are named after all of their columns.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Hours are stored as NUMERIC(4,2): 0.01 .. 99.99.
Hours = Numeric(4, 2)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # All timestamps are timezone-aware and stored as UTC (timestamptz).
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        Decimal: Hours,
    }


def utcnow() -> datetime:
    return datetime.now(UTC)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class TimestampMixin(CreatedAtMixin):
    # Set in Python on update so the new value is known without a refresh
    # (lazy refreshes are not possible with AsyncSession).
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=utcnow)
