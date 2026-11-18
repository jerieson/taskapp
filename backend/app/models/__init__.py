"""All models, imported here so Base.metadata is complete (used by Alembic)."""

from app.models.ai import AIRequest, AISummary
from app.models.auth import Invite, PasswordReset, UserSession
from app.models.enums import AIFeature, Role
from app.models.lookups import (
    Activity,
    ActivityGroup,
    ActivityGroupMember,
    Category,
    DeviationReason,
    OmProject,
    Priority,
    Project,
    Status,
    SupportType,
    WorkSetup,
    project_categories,
)
from app.models.prod_log import ProdLog
from app.models.support import SupportEntry
from app.models.task import Task
from app.models.team import Team
from app.models.user import User

__all__ = [
    "AIFeature",
    "AIRequest",
    "AISummary",
    "Activity",
    "ActivityGroup",
    "ActivityGroupMember",
    "Category",
    "DeviationReason",
    "Invite",
    "OmProject",
    "PasswordReset",
    "Priority",
    "ProdLog",
    "Project",
    "Role",
    "Status",
    "SupportEntry",
    "SupportType",
    "Task",
    "Team",
    "User",
    "UserSession",
    "WorkSetup",
    "project_categories",
]
