"""Idempotent seed: the first admin and the default dropdown values.

Run with `make seed`. Safe to run any number of times:
- The admin is created only if no user has ADMIN_USERNAME or ADMIN_EMAIL. An existing
  admin's password is never changed.
- Each dropdown table is filled only while it is empty, so values the admin has since
  renamed, reordered or deactivated are never duplicated or overwritten.

The labels below exist only in this file. Application code never looks a value up by
its label; it uses the is_default / is_done flags.
"""

import asyncio
import logging
from typing import Any

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.base import Base
from app.db.engine import get_engine, get_sessionmaker
from app.models import Category, Priority, Role, Status, User

logger = logging.getLogger("app.seed")

STATUSES: list[dict[str, Any]] = [
    {"label": "To Do", "is_default": True},
    {"label": "In Progress"},
    {"label": "Blocked"},
    {"label": "Done", "is_done": True},
]
PRIORITIES: list[dict[str, Any]] = [
    {"label": "Low"},
    {"label": "Medium", "is_default": True},
    {"label": "High"},
    {"label": "Urgent"},
]
CATEGORIES: list[dict[str, Any]] = [
    {"label": "Development"},
    {"label": "Bug Fix"},
    {"label": "Code Review"},
    {"label": "Meeting"},
    {"label": "Documentation"},
    {"label": "Research"},
]


class SeedSettings(BaseSettings):
    """ADMIN_* variables. Kept out of app Settings: only the seed needs them."""

    model_config = SettingsConfigDict(extra="ignore")

    admin_username: str
    admin_email: str
    admin_password: SecretStr

    @field_validator("admin_username", "admin_email")
    @classmethod
    def _strip(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("admin_email")
    @classmethod
    def _lowercase(cls, value: str) -> str:
        return value.lower()

    @field_validator("admin_password")
    @classmethod
    def _not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("must not be empty")
        return value


async def _seed_admin(session: AsyncSession, settings: SeedSettings) -> bool:
    taken = await session.scalar(
        select(
            exists().where(
                or_(User.username == settings.admin_username, User.email == settings.admin_email)
            )
        )
    )
    if taken:
        return False
    session.add(
        User(
            username=settings.admin_username,
            email=settings.admin_email,
            password_hash=hash_password(settings.admin_password.get_secret_value()),
            role=Role.ADMIN,
            team_id=None,
        )
    )
    return True


async def _seed_table(session: AsyncSession, model: type[Base], rows: list[dict[str, Any]]) -> int:
    count = await session.scalar(select(func.count()).select_from(model))
    if count:
        return 0
    session.add_all(model(sort_order=i, **row) for i, row in enumerate(rows, start=1))
    return len(rows)


async def seed(session: AsyncSession, settings: SeedSettings) -> dict[str, int]:
    """Insert missing seed data into `session` (flushes, does not commit)."""
    created = {
        "admin": int(await _seed_admin(session, settings)),
        "statuses": await _seed_table(session, Status, STATUSES),
        "priorities": await _seed_table(session, Priority, PRIORITIES),
        "categories": await _seed_table(session, Category, CATEGORIES),
    }
    await session.flush()
    return created


async def main() -> None:
    configure_logging(get_settings().log_level)
    settings = SeedSettings()  # values come from the ADMIN_* environment variables
    try:
        async with get_sessionmaker()() as session, session.begin():
            created = await seed(session, settings)
    finally:
        await get_engine().dispose()
    logger.info("seed_complete", extra={"fields": {"created": created}})


if __name__ == "__main__":
    asyncio.run(main())
