import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models import Category, Priority, Role, Status, User
from app.scripts.seed import CATEGORIES, PRIORITIES, STATUSES, SeedSettings, seed

pytestmark = pytest.mark.anyio

SETTINGS = SeedSettings(
    admin_username="root", admin_email=" Root@Example.com ", admin_password="s3cret-pass"
)


async def _count(db: AsyncSession, model: type, *where: object) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where)) or 0


async def test_seed_twice_creates_no_duplicates(db: AsyncSession) -> None:
    first = await seed(db, SETTINGS)
    second = await seed(db, SETTINGS)

    assert first == {
        "admin": 1,
        "statuses": len(STATUSES),
        "priorities": len(PRIORITIES),
        "categories": len(CATEGORIES),
    }
    assert set(second.values()) == {0}
    assert await _count(db, User) == 1
    assert await _count(db, Status) == len(STATUSES)
    assert await _count(db, Priority) == len(PRIORITIES)
    assert await _count(db, Category) == len(CATEGORIES)


async def test_seed_sets_exactly_one_default_and_a_done_status(db: AsyncSession) -> None:
    await seed(db, SETTINGS)
    assert await _count(db, Status, Status.is_default) == 1
    assert await _count(db, Priority, Priority.is_default) == 1
    assert await _count(db, Status, Status.is_done) == 1
    default_status = await db.scalar(select(Status).where(Status.is_default))
    assert default_status is not None
    assert not default_status.is_done


async def test_seed_admin(db: AsyncSession) -> None:
    await seed(db, SETTINGS)
    admin = await db.scalar(select(User))
    assert admin is not None
    assert admin.username == "root"
    assert admin.email == "root@example.com"
    assert admin.role == Role.ADMIN
    assert admin.team_id is None
    assert admin.is_active
    assert admin.password_hash is not None
    assert verify_password("s3cret-pass", admin.password_hash)


async def test_seed_leaves_admin_edits_alone(db: AsyncSession) -> None:
    await seed(db, SETTINGS)
    status = await db.scalar(select(Status).where(Status.is_default))
    assert status is not None
    status.label = "Renamed by admin"
    admin = await db.scalar(select(User))
    assert admin is not None
    old_hash = admin.password_hash
    await db.flush()

    await seed(db, SETTINGS.model_copy(update={"admin_password": "different"}))

    assert await _count(db, Status) == len(STATUSES)
    assert await _count(db, User) == 1
    assert admin.password_hash == old_hash


async def test_seed_skips_admin_when_email_taken(db: AsyncSession) -> None:
    await seed(db, SETTINGS)
    other = SETTINGS.model_copy(update={"admin_username": "someone-else"})
    assert (await seed(db, other))["admin"] == 0
