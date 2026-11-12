"""Public password reset endpoints (no login required)."""

from typing import Annotated

from fastapi import APIRouter, Path

from app.db.session import SessionDep
from app.schemas.password_resets import PasswordResetCheck, PasswordResetIn
from app.services import password_resets as reset_service

router = APIRouter(prefix="/password-resets", tags=["password-resets"])

Token = Annotated[str, Path(max_length=128)]


@router.get("/{token}", response_model=PasswordResetCheck)
async def check_reset(token: Token, db: SessionDep) -> PasswordResetCheck:
    """Whether the link can still be used (always 200)."""
    return await reset_service.check_reset(db, token)


@router.post("/{token}", status_code=204)
async def use_reset(token: Token, data: PasswordResetIn, db: SessionDep) -> None:
    """Set a new password. Single use; revokes all of the user's sessions."""
    await reset_service.use_reset(db, token, data.new_password)
