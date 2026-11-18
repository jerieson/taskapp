"""Natural-language log entry and planning: turn free text into draft prod log rows
(one or many, e.g. "Tuesday to Friday, 4 hrs a day" = four planned rows). Nothing is
saved; the user reviews the rows and saves them through the bulk create endpoint.

The model only sees the active dropdown values (the same set the log form offers),
and every ID it returns is checked again against those sets and the linked-dropdown
rules before it reaches the client.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIClient
from app.ai.prompts.nl_log_entry import (
    MAX_ENTRIES,
    SYSTEM,
    LogDraftLLM,
    LogEntryLLM,
    build_prompt,
)
from app.core import weeks
from app.core.config import Settings
from app.models import User
from app.models.enums import AIFeature, Role
from app.schemas.ai import LOG_DRAFT_MAX_ROWS, LogDraftField, LogDraftOut, LogDraftRow
from app.schemas.lookups import LogOptionProject, LogOptionsOut
from app.schemas.tasks import Description
from app.services.log_options import get_log_options

MAX_DESCRIPTION = Description.__metadata__[0].max_length or 10000
MAX_RANGE_DAYS = 62
"""A longer range is cut short (the row cap applies anyway)."""


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


@dataclass
class _Refs:
    """An entry's dropdown values after checking them against the linked rules."""

    work_setup_id: int | None
    category_id: int | None
    project_id: int | None
    activity_id: int | None
    om_project_id: int | None


def _clean_refs(raw: LogEntryLLM, linked: _Linked) -> _Refs:
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
    return _Refs(work_setup_id, category_id, project_id, activity_id, om_project_id)


def _days(raw: LogEntryLLM) -> list[date]:
    """The entry's days: one day, or the weekdays of a range (a range of only Saturday
    and Sunday keeps those days). Empty when the start date is unusable."""
    start = _date(raw.date_from)
    if start is None:
        return []
    end = _date(raw.date_to)
    if end is None or end <= start:
        return [start]
    end = min(end, start + timedelta(days=MAX_RANGE_DAYS))
    every = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    return [d for d in every if d.weekday() < 5] or every


def _per_day(value: float | None, raw: LogEntryLLM, days: int) -> float | None:
    if value is None or raw.hours_per != "range" or days <= 1:
        return value
    return value / days


async def draft_log(
    db: AsyncSession,
    ai: AIClient,
    user: User,
    text: str,
    settings: Settings,
) -> LogDraftOut:
    """Draft rows dated before or in a locked week (after its Friday deadline) cannot
    carry planned hours, as in the log service (admins excepted): on today or earlier
    they become actual, unplanned hours; later days lose them and ask for hours.
    Hours above the daily cap (WORKDAY_HOURS) are dropped."""
    max_hours = settings.workday_hours
    today = weeks.today(settings)
    options = await get_log_options(db, max_hours)
    prompt = build_prompt(text=text, today=today, **_prompt_context(options))

    raw = await ai.generate_structured(
        user, AIFeature.NL_LOG_ENTRY, system=SYSTEM, prompt=prompt, schema=LogDraftLLM
    )

    linked = _Linked(options)
    rows: list[LogDraftRow] = []
    for entry in raw.entries[:MAX_ENTRIES]:
        days = _days(entry)
        refs = _clean_refs(entry, linked)
        unclear = entry.hours_per == "unclear" and len(days) > 1
        planned = _hours(_per_day(entry.planned_hours, entry, len(days)), max_hours)
        actual = _hours(_per_day(entry.hours_spent, entry, len(days)), max_hours)
        description = _text(entry.description, MAX_DESCRIPTION)
        for day in days:
            row = LogDraftRow(
                log_date=day,
                is_planned=not entry.is_unplanned,
                work_setup_id=refs.work_setup_id,
                planned_hours=planned,
                hours_spent=actual,
                category_id=refs.category_id,
                project_id=refs.project_id,
                activity_id=refs.activity_id,
                om_project_id=refs.om_project_id,
                description=description,
                missing_fields=[],
            )
            check_hours = unclear
            if row.planned_hours is not None and _locked(day, user, settings):
                if day <= today:
                    row.hours_spent = row.hours_spent or row.planned_hours
                    row.is_planned = False
                else:
                    check_hours = True
                row.planned_hours = None
            row.missing_fields = _missing(row, check_hours)
            rows.append(row)

    rows.sort(key=lambda r: r.log_date)  # stable: entry order within a day
    return LogDraftOut(rows=rows[:LOG_DRAFT_MAX_ROWS])


def _locked(day: date, user: User, settings: Settings) -> bool:
    """Planned hours can no longer be set on this day (admins are exempt)."""
    return user.role != Role.ADMIN and not weeks.plan_week(day, settings).is_open


def _missing(row: LogDraftRow, check_hours: bool) -> list[LogDraftField]:
    missing: list[LogDraftField] = []
    for field in ("work_setup_id", "category_id", "project_id", "activity_id"):
        if getattr(row, field) is None:
            missing.append(field)
    if check_hours or (row.planned_hours is None and row.hours_spent is None):
        missing.append("hours")
    return missing
