"""Database-level guarantees: CHECK constraints, unique indexes and ON DELETE rules."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DailyPlan,
    DailyPlanItem,
    Invite,
    Process,
    ProcessRun,
    ProcessStep,
    Role,
    Status,
    Task,
    Team,
    User,
)
from tests.factories import (
    make_log,
    make_priority,
    make_status,
    make_task,
    make_team,
    make_user,
)

pytestmark = pytest.mark.anyio


@asynccontextmanager
async def violates(session: AsyncSession, constraint: str) -> AsyncIterator[None]:
    """Expect the block to fail on `constraint`; the rest of the test's transaction survives."""
    with pytest.raises(IntegrityError) as exc_info:
        async with session.begin_nested():
            yield
    assert constraint in str(exc_info.value)


# --- prod_logs.hours_spent -------------------------------------------------------------


@pytest.mark.parametrize("hours", ["0", "25", "-1", "24.01"])
async def test_hours_spent_out_of_range_rejected(db: AsyncSession, hours: str) -> None:
    user = await make_user(db)
    async with violates(db, "ck_prod_logs_hours_spent_range"):
        await make_log(db, user=user, hours_spent=Decimal(hours))


@pytest.mark.parametrize("hours", ["0.01", "7.5", "24"])
async def test_hours_spent_in_range_accepted(db: AsyncSession, hours: str) -> None:
    log = await make_log(db, hours_spent=Decimal(hours))
    assert log.hours_spent == Decimal(hours)


# --- single default status / priority --------------------------------------------------


async def test_second_active_default_status_rejected(db: AsyncSession) -> None:
    await make_status(db, is_default=True)
    async with violates(db, "uq_statuses_single_default"):
        await make_status(db, is_default=True)


async def test_second_active_default_priority_rejected(db: AsyncSession) -> None:
    await make_priority(db, is_default=True)
    async with violates(db, "uq_priorities_single_default"):
        await make_priority(db, is_default=True)


async def test_inactive_status_cannot_be_default(db: AsyncSession) -> None:
    async with violates(db, "ck_statuses_default_is_active"):
        await make_status(db, is_default=True, is_active=False)


async def test_default_can_move_to_another_status(db: AsyncSession) -> None:
    old = await make_status(db, is_default=True)
    new = await make_status(db)
    old.is_default = False
    await db.flush()
    new.is_default = True
    await db.flush()
    defaults = (await db.scalars(select(Status.id).where(Status.is_default))).all()
    assert defaults == [new.id]


# --- users -----------------------------------------------------------------------------


async def test_non_admin_requires_team(db: AsyncSession) -> None:
    async with violates(db, "ck_users_team_matches_role"):
        await make_user(db, role=Role.DEV, team_id=None)


async def test_admin_cannot_have_team(db: AsyncSession) -> None:
    team = await make_team(db)
    async with violates(db, "ck_users_team_matches_role"):
        await make_user(db, role=Role.ADMIN, team=team)


async def test_user_needs_a_login_method(db: AsyncSession) -> None:
    async with violates(db, "ck_users_has_login_method"):
        await make_user(db, password_hash=None, google_sub=None)


async def test_invite_role_cannot_be_admin(db: AsyncSession) -> None:
    admin = await make_user(db, role=Role.ADMIN)
    team = await make_team(db)
    async with violates(db, "ck_invites_role_not_admin"):
        db.add(
            Invite(
                email="new@example.com",
                role=Role.ADMIN,
                team_id=team.id,
                token_hash="h",
                expires_at=admin.created_at,
                created_by=admin.id,
            )
        )
        await db.flush()


# --- delete behaviour ------------------------------------------------------------------


async def test_deleting_task_nulls_prod_log_task_id(db: AsyncSession) -> None:
    task = await make_task(db)
    log = await make_log(db, task=task, user=await db.get_one(User, task.user_id))

    await db.execute(delete(Task).where(Task.id == task.id))
    await db.refresh(log)

    assert log.task_id is None


async def test_deleting_task_cascades_daily_plan_items(db: AsyncSession) -> None:
    task = await make_task(db)
    plan = DailyPlan(user_id=task.user_id, plan_date=task.created_at.date())
    db.add(plan)
    await db.flush()
    db.add(DailyPlanItem(daily_plan_id=plan.id, task_id=task.id, item_order=1))
    await db.flush()

    await db.execute(delete(Task).where(Task.id == task.id))

    remaining = await db.scalars(
        select(DailyPlanItem).where(DailyPlanItem.daily_plan_id == plan.id)
    )
    assert remaining.all() == []


async def test_deleting_team_with_users_fails(db: AsyncSession) -> None:
    team = await make_team(db)
    await make_user(db, team=team)
    async with violates(db, "fk_users_team_id_teams"):
        await db.execute(delete(Team).where(Team.id == team.id))


async def test_deleting_team_with_prod_logs_fails(db: AsyncSession) -> None:
    old_team, new_team = await make_team(db), await make_team(db)
    user = await make_user(db, team=old_team)
    await make_log(db, user=user)
    user.team_id = new_team.id  # the log keeps old_team as its snapshot
    await db.flush()

    async with violates(db, "fk_prod_logs_team_id_teams"):
        await db.execute(delete(Team).where(Team.id == old_team.id))


async def test_deleting_unused_team_succeeds(db: AsyncSession) -> None:
    team = await make_team(db)
    await db.execute(delete(Team).where(Team.id == team.id))
    assert (await db.scalars(select(Team.id).where(Team.id == team.id))).all() == []


async def _process_with_step(db: AsyncSession) -> tuple[User, Process, ProcessStep]:
    user = await make_user(db)
    process = Process(owner_id=user.id, name="Release")
    db.add(process)
    await db.flush()
    step = ProcessStep(process_id=process.id, step_order=1, title="Tag release")
    db.add(step)
    await db.flush()
    return user, process, step


async def test_deleting_process_step_nulls_task_step_id(db: AsyncSession) -> None:
    user, process, step = await _process_with_step(db)
    run = ProcessRun(process_id=process.id, user_id=user.id)
    db.add(run)
    await db.flush()
    task = await make_task(db, user=user, process_run_id=run.id, process_step_id=step.id)

    await db.execute(delete(ProcessStep).where(ProcessStep.id == step.id))
    await db.refresh(task)

    assert task.process_step_id is None
    assert task.process_run_id == run.id


async def test_deleting_process_with_runs_fails(db: AsyncSession) -> None:
    user, process, _ = await _process_with_step(db)
    db.add(ProcessRun(process_id=process.id, user_id=user.id))
    await db.flush()
    async with violates(db, "fk_process_runs_process_id_processes"):
        await db.execute(delete(Process).where(Process.id == process.id))


async def test_deleting_process_without_runs_removes_steps(db: AsyncSession) -> None:
    _, process, step = await _process_with_step(db)
    await db.execute(delete(Process).where(Process.id == process.id))
    remaining = await db.scalars(select(ProcessStep.id).where(ProcessStep.id == step.id))
    assert remaining.all() == []
