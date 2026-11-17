"""Checks for references to dropdown values and projects on user records."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Category, Priority, Project, Status

type RefModel = type[Category] | type[Status] | type[Priority] | type[Project]

# Request field -> (model, noun used in messages)
REFS: dict[str, tuple[RefModel, str]] = {
    "status_id": (Status, "status"),
    "priority_id": (Priority, "priority"),
    "category_id": (Category, "category"),
    "project_id": (Project, "project"),
}


def invalid_reference(field: str, message: str) -> AppError:
    return AppError(422, "invalid_reference", message, fields={field: message})


async def check_ref(
    db: AsyncSession, field: str, value: int, keep: int | None, *, error_field: str | None = None
) -> None:
    """The referenced row must exist and be active, unless it is `keep` (the value
    already on the record, which may stay after being deactivated).

    `field` picks the kind of reference (a key of REFS); the error is reported on
    `error_field` when given (e.g. `steps.2.default_category_id`), else on `field`."""
    model, noun = REFS[field]
    row = await db.get(model, value)
    if row is None or (not row.is_active and value != keep):
        raise invalid_reference(error_field or field, f"Choose an active {noun}")
