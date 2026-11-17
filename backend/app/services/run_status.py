"""Keeps a process run's status in step with its tasks.

Kept apart from `services.process_runs` so `services.tasks` can call it without a
circular import.

- An in-progress run completes when it has tasks and every one of them is done.
- A completed run goes back to in progress when one of its tasks is reopened (or a
  new open task appears in it).
- A cancelled run never changes here; cancelling keeps its tasks as they are.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import ProcessRun, RunStatus, Status, Task

logger = logging.getLogger("app.process_runs")


async def run_progress(db: AsyncSession, run_id: int) -> tuple[int, int]:
    """(done, total) task counts for one run."""
    row = (
        await db.execute(
            select(func.count(Task.id).filter(Status.is_done), func.count(Task.id))
            .select_from(Task)
            .join(Status, Status.id == Task.status_id)
            .where(Task.process_run_id == run_id)
        )
    ).one()
    return row[0], row[1]


async def sync_run_status(db: AsyncSession, run_id: int) -> None:
    """Recompute the run's status from its tasks. Call before committing a change to
    a run task's status, or after deleting one. Locks the run row."""
    await db.flush()
    run = await db.scalar(select(ProcessRun).where(ProcessRun.id == run_id).with_for_update())
    if run is None or run.status == RunStatus.CANCELLED:
        return
    done, total = await run_progress(db, run_id)
    all_done = total > 0 and done == total
    if all_done and run.status == RunStatus.IN_PROGRESS:
        run.status = RunStatus.COMPLETED
        run.completed_at = utcnow()
        logger.info("run_completed", extra={"fields": {"run_id": run_id}})
    elif not all_done and run.status == RunStatus.COMPLETED:
        run.status = RunStatus.IN_PROGRESS
        run.completed_at = None
        logger.info("run_reopened", extra={"fields": {"run_id": run_id}})
