"""Admin import of the team's support dictionary sheet (a CSV export).

Columns are found by header (case, spaces and punctuation ignored): Type, Project,
Module, Sub-module, Concern, Cause, Resolution, Query, Notes, Date Inputted, and the
author column (headed "Author", or the first column when its header is none of these;
the team's export heads it "0"). Type and Concern are required columns.

Per row:
- Cells are trimmed; a cell made only of dashes and spaces ("- - - -") is blank.
- Completely empty rows are ignored; a row with a blank concern is skipped.
- Type: an existing type with the same label (case-insensitive), else the one existing
  type whose label starts with it ("Data Modif" -> "Data Modification"), else a new
  type is created.
- Author: a matching username (case-insensitive) becomes the entry's author; otherwise
  the importing admin is the author and "Author: <name>" is added to the notes.
- Date Inputted (M/D/YYYY), when present, becomes the creation date (noon in
  APP_TIMEZONE); otherwise the import time.
- A row with the same type, project, module, sub-module and concern as an existing
  entry (or an earlier row) is skipped, so importing the same file twice creates
  nothing new. (The sheet repeats concerns under different modules; those are kept.)

Everything happens in one transaction; with `dry_run` it is rolled back (preview).
"""

import csv
import io
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models import SupportEntry, SupportType, User
from app.schemas.support import (
    CONCERN_MAX,
    PLACE_MAX,
    QUERY_MAX,
    TEXT_MAX,
    ImportRowError,
    SupportImportOut,
    TypeMatch,
)
from app.services.lookups import lock_table

logger = logging.getLogger("app.support_import")

MAX_FILE_BYTES = 2_000_000
TYPE_LABEL_MAX = 50

# Normalised header -> field.
_HEADERS = {
    "author": "author",
    "type": "type",
    "project": "project",
    "module": "module",
    "submodule": "sub_module",
    "concern": "concern",
    "cause": "cause",
    "resolution": "resolution",
    "query": "query",
    "notes": "notes",
    "dateinputted": "date",
}
_LIMITS = {
    "project": PLACE_MAX,
    "module": PLACE_MAX,
    "sub_module": PLACE_MAX,
    "concern": CONCERN_MAX,
    "cause": TEXT_MAX,
    "resolution": TEXT_MAX,
    "query": QUERY_MAX,
    "notes": TEXT_MAX,
}
_LABELS = {
    "project": "Project",
    "module": "Module",
    "sub_module": "Sub-module",
    "concern": "Concern",
    "cause": "Cause",
    "resolution": "Resolution",
    "query": "Query",
    "notes": "Notes",
}
_DASHES = re.compile(r"[\s\-\u2013\u2014]*")


def _invalid_file(message: str) -> AppError:
    return AppError(422, "invalid_file", message, fields={"file": message})


def _norm_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def _clean(value: str, *, keep_indent: bool = False) -> str:
    if _DASHES.fullmatch(value):
        return ""
    if keep_indent:  # SQL: keep the first line's indentation
        return value.strip("\r\n").rstrip()
    return value.strip()


def _parse_date(value: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _read(content: bytes) -> tuple[dict[str, int], list[list[str]]]:
    """Map field -> column index, and the data rows."""
    if len(content) > MAX_FILE_BYTES:
        raise _invalid_file("The file is larger than 2 MB")
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

    columns: dict[str, int] = {}
    for index, header in enumerate(rows[0]):
        field = _HEADERS.get(_norm_header(header))
        if field and field not in columns:
            columns[field] = index
    if "author" not in columns and _norm_header(rows[0][0]) not in _HEADERS:
        columns["author"] = 0
    missing = [name for name in ("type", "concern") if name not in columns]
    if missing:
        names = " and ".join(name.capitalize() for name in missing)
        raise _invalid_file(f"The file has no {names} column")
    return columns, rows[1:]


@dataclass
class _Types:
    """Support types by label, creating missing ones on demand."""

    db: AsyncSession
    rows: list[SupportType]
    result: SupportImportOut

    def __post_init__(self) -> None:
        self.by_key = {row.label.lower(): row for row in self.rows}
        self.next_order = max((row.sort_order for row in self.rows), default=0) + 1

    async def get(self, label: str) -> SupportType | str:
        """The type for `label`, or an error message."""
        key = label.lower()
        if key in self.by_key:
            return self.by_key[key]
        prefixed = [row for k, row in self.by_key.items() if k.startswith(key)]
        if len(prefixed) == 1:
            row = prefixed[0]
            self.by_key[key] = row
            self.result.types_matched.append(TypeMatch(file_label=label, type_label=row.label))
            return row
        if len(label) > TYPE_LABEL_MAX:
            return f"Type is longer than {TYPE_LABEL_MAX} characters"
        row = SupportType(label=label, sort_order=self.next_order, is_active=True)
        self.next_order += 1
        self.db.add(row)
        await self.db.flush()
        self.by_key[key] = row
        self.result.types_created.append(label)
        return row


def _dup_key(
    type_id: int, project: str | None, module: str | None, sub_module: str | None, concern: str
) -> tuple[int, str, str, str, str]:
    def norm(value: str | None) -> str:
        return " ".join((value or "").lower().split())

    return (type_id, norm(project), norm(module), norm(sub_module), norm(concern))


async def import_support(
    db: AsyncSession, admin: User, content: bytes, settings: Settings, *, dry_run: bool
) -> SupportImportOut:
    columns, rows = _read(content)
    result = SupportImportOut(
        dry_run=dry_run,
        created=0,
        skipped=0,
        types_created=[],
        types_matched=[],
        authors_matched=[],
        authors_unmatched=[],
        errors=[],
    )

    await lock_table(db, SupportType.__tablename__)
    types = _Types(db, list(await db.scalars(select(SupportType))), result)
    users = {u.username.lower(): u for u in await db.scalars(select(User))}
    seen: dict[tuple[int, str, str, str, str], str] = {
        _dup_key(
            e.type_id, e.project, e.module, e.sub_module, e.concern
        ): "Already in the dictionary"
        for e in await db.scalars(select(SupportEntry))
    }
    now = datetime.now(settings.tz)

    def skip(line: int, message: str) -> None:
        result.skipped += 1
        result.errors.append(ImportRowError(row=line, message=message))

    for line, raw in enumerate(rows, start=2):
        cells = {
            field: _clean(raw[index], keep_indent=field == "query") if index < len(raw) else ""
            for field, index in columns.items()
        }
        if not any(cells.values()):
            continue
        if not cells["concern"]:
            skip(line, "Concern is blank")
            continue
        if not cells["type"]:
            skip(line, "Type is blank")
            continue

        author_name = cells.get("author", "")
        author = users.get(author_name.lower()) if author_name else None
        notes = cells.get("notes", "")
        if author_name and author is None:
            notes = f"{notes}\n\nAuthor: {author_name}" if notes else f"Author: {author_name}"

        values = {field: cells.get(field) or None for field in _LIMITS}
        values["notes"] = notes or None
        too_long = [
            f"{_LABELS[field]} is longer than {limit} characters"
            for field, limit in _LIMITS.items()
            if values[field] is not None and len(values[field] or "") > limit
        ]
        if too_long:
            skip(line, "; ".join(too_long))
            continue

        type_ = await types.get(cells["type"])
        if isinstance(type_, str):
            skip(line, type_)
            continue

        key = _dup_key(
            type_.id, values["project"], values["module"], values["sub_module"], cells["concern"]
        )
        if key in seen:
            skip(line, seen[key])
            continue
        seen[key] = f"Same as row {line}"

        if author is not None and author.username not in result.authors_matched:
            result.authors_matched.append(author.username)
        if author_name and author is None and author_name not in result.authors_unmatched:
            result.authors_unmatched.append(author_name)

        inputted = _parse_date(cells.get("date", ""))
        created_at = datetime.combine(inputted, time(12), settings.tz) if inputted else now
        db.add(
            SupportEntry(
                type_id=type_.id,
                **values,
                created_by=author.id if author else admin.id,
                updated_by=admin.id,
                created_at=created_at,
                updated_at=now,
            )
        )
        result.created += 1

    await db.flush()
    if dry_run:
        await db.rollback()
    else:
        await db.commit()
        logger.info(
            "support_imported",
            extra={"fields": {"created": result.created, "skipped": result.skipped}},
        )
    return result
