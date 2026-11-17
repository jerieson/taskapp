"""Import of the productivity-log sheet's "Data" tab (a CSV export).

Every column is a list of values under its header:

- A header without "_" names a category; its values are that category's projects.
- `<Category>_Project` lists the O&M projects ("Project (For O&M)") and marks that
  category as offering them.
- `<Category>_<Project>` is the activity group of that project (matched ignoring case
  and spaces, so `Others_AdminWork` belongs to "Admin Work"). When no project in that
  category matches, the group is still imported, linked to no project.
- `OM_Reflected_Activity` / `OM_Not_Reflected_Activity` are the groups of the projects
  whose names say "Reflected" / "Not Reflected".
- `Project_Activity` is the group of every other project in the file (the enhancement
  projects, which have no column of their own).

The import is idempotent: values are matched by label, case-insensitively and with
spaces trimmed; existing values are reused (inactive ones stay inactive) and nothing is
deleted or renamed. A project that already has a different group keeps it and is
reported. Everything happens in one transaction.
"""

import csv
import io
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import (
    Activity,
    ActivityGroup,
    ActivityGroupMember,
    Category,
    OmProject,
    Project,
)
from app.schemas.lookups import (
    DataTabImportOut,
    GroupConflict,
    ImportCounts,
    ImportLinks,
)
from app.services.lookups import NOUN, lock_table

logger = logging.getLogger("app.data_import")

MAX_FILE_BYTES = 1_000_000

_FALLBACK_GROUP = "project_activity"
_OM_GROUPS = {"om_reflected_activity": False, "om_not_reflected_activity": True}


def _key(label: str) -> str:
    """Label matching: case-insensitive, surrounding spaces trimmed."""
    return label.strip().lower()


def _squash(text: str) -> str:
    """Header matching: case- and space-insensitive."""
    return "".join(text.split()).lower()


def _invalid_file(message: str) -> AppError:
    return AppError(422, "invalid_file", message, fields={"file": message})


@dataclass
class _Column:
    header: str
    values: list[str]
    """Non-empty values, trimmed, first occurrence of each (case-insensitive)."""


def _parse(content: bytes) -> list[_Column]:
    if len(content) > MAX_FILE_BYTES:
        raise _invalid_file("The file is larger than 1 MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _invalid_file("Save the sheet as a UTF-8 CSV file") from exc
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise _invalid_file("The file is not a valid CSV file") from exc
    if not rows or not any(cell.strip() for cell in rows[0]):
        raise _invalid_file("The file has no header row")

    columns: list[_Column] = []
    for index, header in enumerate(rows[0]):
        seen: set[str] = set()
        values: list[str] = []
        for row in rows[1:]:
            value = row[index].strip() if index < len(row) else ""
            if value and _key(value) not in seen:
                seen.add(_key(value))
                values.append(value)
        if header.strip() or values:
            columns.append(_Column(header.strip() or f"(column {index + 1})", values))
    return columns


class _Values:
    """Existing rows of one table by label key; creates missing ones on demand."""

    def __init__(
        self,
        db: AsyncSession,
        model: Any,
        rows: list[Any],
        attr: str,
        max_length: int,
        result: DataTabImportOut,
        counter: str,
    ) -> None:
        self.db = db
        self.model = model
        self.attr = attr
        self.max_length = max_length
        self.result = result
        self.counter = counter
        self.by_key = {_key(getattr(row, attr)): row for row in rows}
        self.next_order = max((getattr(row, "sort_order", 0) for row in rows), default=0) + 1

    def check_length(self, label: str, errors: list[str]) -> None:
        if len(label) > self.max_length:
            errors.append(f"“{label}” is longer than {self.max_length} characters")

    def get(self, label: str) -> Any:
        row = self.by_key.get(_key(label))
        if row is not None:
            if not row.is_active:
                note = f"{NOUN.get(self.model, 'project')}: {getattr(row, self.attr)}"
                if note not in self.result.inactive_reused:
                    self.result.inactive_reused.append(note)
            return row
        values: dict[str, Any] = {self.attr: label, "is_active": True}
        if self.model is Project:
            values["description"] = ""
            values["categories"] = []
        else:
            values["sort_order"] = self.next_order
            self.next_order += 1
        row = self.model(**values)
        if self.model is ActivityGroup:
            row.members = []
        self.db.add(row)
        self.by_key[_key(label)] = row
        counts = self.result.created
        setattr(counts, self.counter, getattr(counts, self.counter) + 1)
        return row


@dataclass
class _Plan:
    """Columns sorted by meaning."""

    categories: list[_Column] = field(default_factory=list)
    om_projects: list[tuple[_Column, _Column]] = field(default_factory=list)
    """(category column, O&M project column)"""
    project_groups: list[tuple[_Column, _Column, str]] = field(default_factory=list)
    """(category column, group column, project part of the header)"""
    om_groups: list[tuple[_Column, bool]] = field(default_factory=list)
    """(group column, True for the "Not Reflected" group)"""
    fallback_group: _Column | None = None


def _plan(columns: list[_Column], result: DataTabImportOut) -> _Plan:
    plan = _Plan()
    plan.categories = [c for c in columns if "_" not in c.header and c.values]
    category_by_header = {_squash(c.header): c for c in plan.categories}
    for column in columns:
        if column in plan.categories:
            continue
        if not column.values:
            result.empty_columns.append(column.header)
            continue
        squashed = _squash(column.header)
        if squashed == _FALLBACK_GROUP and plan.fallback_group is None:
            plan.fallback_group = column
            continue
        if squashed in _OM_GROUPS:
            plan.om_groups.append((column, _OM_GROUPS[squashed]))
            continue
        category_part, _, project_part = column.header.partition("_")
        category = category_by_header.get(_squash(category_part))
        if category is None:
            result.unrecognised_columns.append(column.header)
        elif _squash(project_part) == "project":
            plan.om_projects.append((category, column))
        else:
            plan.project_groups.append((category, column, project_part))
    return plan


def _group_columns(plan: _Plan) -> list[_Column]:
    columns = [group for _, group, _ in plan.project_groups]
    columns += [group for group, _ in plan.om_groups]
    if plan.fallback_group is not None:
        columns.append(plan.fallback_group)
    return columns


async def _load[M](db: AsyncSession, model: type[M]) -> list[M]:
    return list((await db.scalars(select(model))).all())


async def import_data_tab(db: AsyncSession, content: bytes) -> DataTabImportOut:
    columns = _parse(content)
    result = DataTabImportOut(
        created=ImportCounts(),
        linked=ImportLinks(),
        group_conflicts=[],
        unlinked_groups=[],
        inactive_reused=[],
        unrecognised_columns=[],
        empty_columns=[],
    )
    plan = _plan(columns, result)
    if not plan.categories:
        raise _invalid_file("No category columns found. Upload the sheet's Data tab.")

    for table in ("categories", "projects", "activities", "activity_groups", "om_projects"):
        await lock_table(db, table)
    categories = _Values(db, Category, await _load(db, Category), "label", 50, result, "categories")
    projects = _Values(db, Project, await _load(db, Project), "name", 100, result, "projects")
    activities = _Values(
        db, Activity, await _load(db, Activity), "label", 100, result, "activities"
    )
    groups = _Values(
        db, ActivityGroup, await _load(db, ActivityGroup), "label", 50, result, "activity_groups"
    )
    om_projects = _Values(
        db, OmProject, await _load(db, OmProject), "label", 100, result, "om_projects"
    )

    group_columns = _group_columns(plan)
    errors: list[str] = []
    for column in plan.categories:
        categories.check_length(column.header, errors)
        for value in column.values:
            projects.check_length(value, errors)
    for _, column in plan.om_projects:
        for value in column.values:
            om_projects.check_length(value, errors)
    for column in group_columns:
        groups.check_length(column.header, errors)
        for value in column.values:
            activities.check_length(value, errors)
    if errors:
        more = f" (and {len(errors) - 5} more)" if len(errors) > 5 else ""
        raise _invalid_file("; ".join(errors[:5]) + more)

    # Categories and their projects. `listed` keeps the file's projects in file order,
    # with the category columns each one appears under.
    listed: dict[str, tuple[Project, list[_Column]]] = {}
    for column in plan.categories:
        category = categories.get(column.header)
        for name in column.values:
            project = projects.get(name)
            if category not in project.categories:
                project.categories.append(category)
                result.linked.project_categories += 1
            listed.setdefault(_key(name), (project, []))[1].append(column)

    # O&M projects; their category offers "Project (For O&M)".
    for category_column, column in plan.om_projects:
        category = categories.get(category_column.header)
        if not category.requires_om_project:
            category.requires_om_project = True
            result.linked.om_flags += 1
        for label in column.values:
            om_projects.get(label)

    # Activity groups and their ordered members.
    for column in group_columns:
        groups.get(column.header)
        for label in column.values:
            activities.get(label)
    await db.flush()  # ids for new groups and activities

    for column in group_columns:
        group = groups.get(column.header)
        member_ids = {member.activity_id for member in group.members}
        position = max((member.sort_order for member in group.members), default=0)
        for label in column.values:
            activity = activities.get(label)
            if activity.id not in member_ids:
                position += 1
                group.members.append(
                    ActivityGroupMember(activity_id=activity.id, sort_order=position)
                )
                member_ids.add(activity.id)
                result.linked.group_activities += 1

    # Which project each group belongs to.
    group_by_id = {group.id: group for group in groups.by_key.values()}
    has_own_group: set[int] = set()

    def assign(group_column: _Column, project: Project) -> None:
        group = groups.get(group_column.header)
        has_own_group.add(id(project))
        if project.activity_group_id is None:
            project.activity_group_id = group.id
            result.linked.project_groups += 1
        elif project.activity_group_id != group.id:
            current = group_by_id[project.activity_group_id]
            result.group_conflicts.append(
                GroupConflict(
                    project=project.name, current_group=current.label, file_group=group.label
                )
            )

    for category_column, group_column, project_part in plan.project_groups:
        matches = [
            project
            for project, under in listed.values()
            if category_column in under and _squash(project.name) == _squash(project_part)
        ]
        for project in matches:
            assign(group_column, project)
        if not matches:
            result.unlinked_groups.append(group_column.header)

    for group_column, not_reflected in plan.om_groups:
        matches = [
            project
            for project, _ in listed.values()
            if "reflected" in _squash(project.name)
            and ("notreflected" in _squash(project.name)) == not_reflected
        ]
        for project in matches:
            assign(group_column, project)
        if not matches:
            result.unlinked_groups.append(group_column.header)

    if plan.fallback_group is not None:
        rest = [p for p, _ in listed.values() if id(p) not in has_own_group]
        for project in rest:
            assign(plan.fallback_group, project)
        if not rest:
            result.unlinked_groups.append(plan.fallback_group.header)

    await db.commit()
    logger.info(
        "data_tab_imported",
        extra={
            "fields": {
                "created": result.created.model_dump(),
                "linked": result.linked.model_dump(),
                "conflicts": len(result.group_conflicts),
            }
        },
    )
    return result
