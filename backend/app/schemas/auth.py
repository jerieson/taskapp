import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models import Role

PASSWORD_MIN_LENGTH = 8
# Argon2 hashes any length, but unbounded input is a cheap way to burn CPU.
PASSWORD_MAX_LENGTH = 128
USERNAME_PATTERN = r"^[A-Za-z0-9._-]{3,50}$"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not _EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address")
    return value


# Emails are stored lowercase; uniqueness checks rely on it.
Email = Annotated[str, AfterValidator(_normalize_email)]
NewPassword = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]
Username = Annotated[
    str,
    Field(
        pattern=USERNAME_PATTERN,
        description="3-50 characters: letters, digits, dot, underscore, hyphen.",
    ),
]


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    new_password: NewPassword


class CsrfOut(BaseModel):
    csrf_token: str


class TeamRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class MeOut(BaseModel):
    id: int
    username: str
    email: str
    role: Role
    team: TeamRef | None
    has_password: bool
    google_linked: bool
    created_at: datetime
