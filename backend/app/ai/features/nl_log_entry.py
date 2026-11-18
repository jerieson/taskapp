"""Natural-language log entry: turn free text into a draft prod log row. Nothing is
saved; the frontend pre-fills the normal log form and the user confirms.

The model only sees the active dropdown values (the same set the log form offers),
and every ID it returns is checked again against those sets and the linked-dropdown
rules before it reaches the client.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIClient
from app.ai.prompts.nl_log_entry import SYSTEM, LogDraftLLM, build_prompt
from app.models import User
from app.models.enums import AIFeature
from app.schemas.ai import LogDraftField, LogDraftOut
from app.schemas.lookups import LogOptionProject, LogOptionsOut
from app.schemas.tasks import Description
from app.services.log_options import get_log_options

MAX_DESCRIPTION = Description.__metadata__[0].max_length or 10000


def _text(value: str | None, max_length: int) -> str | None:
    value = (value or "").strip()
    return value[:max_length].rstrip() or None


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value.strip()) if value else None
    except ValueError:
        return None


def _hours(value: float | None, max_hours: Decimal) -> Decimal | None:
    """Rounded to 0.01; None unless it is a usable log value (0 < h <= max_hours)."""
    if value is None:
        return None
    try:
        hours = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:  # nan / inf
        return None
    return hours if Decimal(0) < hours <= max_hours else None


def _prompt_context(options: LogOptionsOut) -> dict[str, list[dict[str, object]]]:
    return {
        "categories": [
            {"id": c.id, "label": c.label, "offers_om_project": c.requires_om_project}
            for c in options.categories
        ],
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "category_ids": p.category_ids,
                "activity_group_id": p.activity_group_id,
            }
            for p in options.projects
        ],
        "activity_groups": [
            {"id": g.id, "activity_ids": g.activity_ids} for g in options.activity_groups
        ],
        "activities": [{"id": a.id, "label": a.label} for a in options.activities],
        "om_projects": [{"id": o.id, "label": o.label} for o in options.om_projects],
        "work_setups": [{"id": w.id, "label": w.label} for w in options.work_setups],
    }


class _Linked:
    """The active values and their links, as the log form sees them."""

    def __init__(self, options: LogOptionsOut) -> None:
        self.categories = {c.id: c for c in options.categories}
        self.projects: dict[int, LogOptionProject] = {p.id: p for p in options.projects}
        self.activities = {a.id for a in options.activities}
        self.om_projects = {o.id for o in options.om_projects}
        self.work_setups = {w.id for w in options.work_setups}
        self.default_work_setup = next((w.id for w in options.work_setups if w.is_default), None)
        self.group_activities = {g.id: set(g.activity_ids) for g in options.activity_groups}

    def project_fits(self, project_id: int | None, category_id: int | None) -> bool:
        project = self.projects.get(project_id) if project_id is not None else None
        if project is None:
            return False
        return category_id is None or category_id in project.category_ids

    def activity_fits(self, activity_id: int, project_id: int | None) -> bool:
        if project_id is None:
            return True  # nothing to check against yet; the form asks for a project
        group = self.projects[project_id].activity_group_id
        return group is not None and activity_id in self.group_activities.get(group, set())


async def draft_log(
    db: AsyncSession, ai: AIClient, user: User, text: str, today: date, max_hours: Decimal
) -> LogDraftOut:
    """`max_hours` is the daily cap (WORKDAY_HOURS): larger hours are dropped."""
    options = await get_log_options(db, max_hours)
    prompt = build_prompt(text=text, today=today, **_prompt_context(options))

    raw = await ai.generate_structured(
        user, AIFeature.NL_LOG_ENTRY, system=SYSTEM, prompt=prompt, schema=LogDraftLLM
    )

    linked = _Linked(options)
    category_id = raw.category_id if raw.category_id in linked.categories else None
    project_id = raw.project_id if linked.project_fits(raw.project_id, category_id) else None
    if category_id is None and project_id is not None:
        only = linked.projects[project_id].category_ids
        category_id = only[0] if len(only) == 1 else None
    activity_id = raw.activity_id if raw.activity_id in linked.activities else None
    if activity_id is not None and not linked.activity_fits(activity_id, project_id):
        activity_id = None
    om_project_id = raw.om_project_id if raw.om_project_id in linked.om_projects else None
    category = linked.categories.get(category_id) if category_id is not None else None
    if category is None or not category.requires_om_project:
        om_project_id = None
    work_setup_id = (
        raw.work_setup_id if raw.work_setup_id in linked.work_setups else None
    ) or linked.default_work_setup

    draft = LogDraftOut(
        log_date=_date(raw.log_date),
        work_setup_id=work_setup_id,
        planned_hours=_hours(raw.planned_hours, max_hours),
        hours_spent=_hours(raw.hours_spent, max_hours),
        category_id=category_id,
        project_id=project_id,
        activity_id=activity_id,
        om_project_id=om_project_id,
        description=_text(raw.description, MAX_DESCRIPTION),
        missing_fields=[],
    )
    draft.missing_fields = _missing(draft)
    return draft


def _missing(draft: LogDraftOut) -> list[LogDraftField]:
    missing: list[LogDraftField] = []
    for field in ("log_date", "work_setup_id", "category_id", "project_id", "activity_id"):
        if getattr(draft, field) is None:
            missing.append(field)
    if draft.planned_hours is None and draft.hours_spent is None:
        missing.append("hours")
    return missing
