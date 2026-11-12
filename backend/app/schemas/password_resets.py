from datetime import datetime

from pydantic import BaseModel

from app.schemas.auth import NewPassword


class PasswordResetCreated(BaseModel):
    reset_url: str
    """Shown only once: the database stores only a hash of the token."""
    expires_at: datetime


class PasswordResetCheck(BaseModel):
    valid: bool
    username: str | None = None
    expires_at: datetime | None = None


class PasswordResetIn(BaseModel):
    new_password: NewPassword
