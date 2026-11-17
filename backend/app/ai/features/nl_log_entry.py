"""Natural-language log entry: turn free text into a draft prod log. Nothing is saved;
the frontend pre-fills the normal log form and the user confirms.

The model only sees the caller's own open tasks and active categories/projects, and
every ID it returns is checked again against those sets before it reaches the client.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIClient
from app.ai.prompts.nl_log_entry import SYSTEM, LogDraftLLM, build_prompt
from app.models import Category, Project, Status, Task, User
from app.models.enums import AIFeature
from app.schemas.ai import LogDraftField, LogDraftOut
from app.schemas.prod_logs import MAX_DAILY_HOURS
from app.schemas.tasks import Description, Title

# Bounds the prompt size for users with very many open tasks (most recent first).
MAX_TASKS_IN_PROMPT = 100
MAX_TITLE = Title.__metadata__[0].max_length or 200
MAX_DESCRIPTION = Description.__metadata__[0].max_length or 10000

_REQUIRED: tuple[LogDraftField, ...] = ("title", "log_date", "hours_spent", "category_id")


async def _active_categories(db: AsyncSession) -> dict[int, str]:
    rows = await db.execute(
        select(Category.id, Category.label)
        .where(Category.is_active)
        .order_by(Category.sort_order, Category.id)
    )
    return {row.id: row.label for row in rows}


async def _active_projects(db: AsyncSession) -> dict[int, str]:
    rows = await db.execute(
        select(Project.id, Project.name).where(Project.is_active).order_by(Project.name)
    )
    return {row.id: row.name for row in rows}


async def _open_tasks(db: AsyncSession, user: User) -> dict[int, Task]:
    rows = await db.scalars(
        select(Task)
        .join(Status, Status.id == Task.status_id)
        .where(Task.user_id == user.id, ~Status.is_done)
        .order_by(Task.updated_at.desc(), Task.id.desc())
        .limit(MAX_TASKS_IN_PROMPT)
    )
    return {t.id: t for t in rows}


def _text(value: str | None, max_length: int) -> str | None:
    value = (value or "").strip()
    return value[:max_length].rstrip() or None


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value.strip()) if value else None
    except ValueError:
        return None


def _hours(value: float | None) -> Decimal | None:
    """Rounded to 0.01; None unless it is a usable log value (0 < h <= 24)."""
    if value is None:
        return None
    try:
        hours = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:  # nan / inf
        return None
    return hours if Decimal(0) < hours <= MAX_DAILY_HOURS else None


def _pick(value: int | None, allowed: dict[int, object]) -> int | None:
    return value if value in allowed else None


async def draft_log(
    db: AsyncSession, ai: AIClient, user: User, text: str, today: date
) -> LogDraftOut:
    categories = await _active_categories(db)
    projects = await _active_projects(db)
    tasks = await _open_tasks(db, user)
    task_info = {t.id: (t.project_id, t.category_id) for t in tasks.values()}
    prompt = build_prompt(
        text=text,
        today=today,
        categories=list(categories.items()),
        projects=list(projects.items()),
        tasks=[(t.id, t.title) for t in tasks.values()],
    )

    raw = await ai.generate_structured(
        user, AIFeature.NL_LOG_ENTRY, system=SYSTEM, prompt=prompt, schema=LogDraftLLM
    )

    task_id = _pick(raw.task_id, task_info)
    project_id = _pick(raw.project_id, projects)
    category_id = _pick(raw.category_id, categories)
    if task_id is not None:
        # Same as the log form: a chosen task pre-fills project and category.
        task_project, task_category = task_info[task_id]
        project_id = project_id or _pick(task_project, projects)
        category_id = category_id or _pick(task_category, categories)

    draft = LogDraftOut(
        title=_text(raw.title, MAX_TITLE),
        description=_text(raw.description, MAX_DESCRIPTION),
        log_date=_date(raw.log_date),
        hours_spent=_hours(raw.hours_spent),
        task_id=task_id,
        project_id=project_id,
        category_id=category_id,
        missing_fields=[],
    )
    draft.missing_fields = [f for f in _REQUIRED if getattr(draft, f) is None]
    return draft
