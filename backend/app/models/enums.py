from enum import StrEnum

from sqlalchemy import Enum


class Role(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    DEV = "dev"


class RunStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AIFeature(StrEnum):
    NL_LOG_ENTRY = "nl_log_entry"
    DAILY_PLAN = "daily_plan"
    TEAM_SUMMARY = "team_summary"


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """VARCHAR column restricted by a CHECK constraint (ck_<table>_<name>).

    Chosen over native Postgres ENUM types so adding a value later is a plain
    constraint swap in a migration instead of ALTER TYPE.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
