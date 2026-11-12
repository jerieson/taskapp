"""Google OAuth (authorization code flow with PKCE) and the Google login rules.

Rules (CLAUDE.md, Auth):
- Google must report email_verified = true.
- The email must match an existing active user or a pending invite; otherwise reject.
- A password user signing in with the same verified email gets google_sub linked.
- Started from an invite link, the Google email must equal the invite email.
"""

import logging
import re
from typing import Annotated

from authlib.integrations.httpx_client import AsyncOAuth2Client, OAuthError
from fastapi import Depends
from httpx2 import AsyncBaseTransport, HTTPError
from pydantic import BaseModel, ValidationError
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, SettingsDep
from app.core.errors import AppError
from app.models import User
from app.services.auth import NewSession, create_session
from app.services.invites import (
    create_user_from_invite,
    find_pending_invite_by_email,
    find_pending_invite_by_token,
)

logger = logging.getLogger("app.google")

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - a URL, not a secret
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPE = "openid email profile"


class GoogleUserInfo(BaseModel):
    sub: str
    email: str
    email_verified: bool = False


class GoogleOAuthError(Exception):
    """The code exchange or the userinfo request failed."""


class GoogleOAuthClient:
    """Thin wrapper around Authlib so tests can replace the network calls."""

    def __init__(self, settings: Settings, transport: AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        # Tests pass an httpx2.MockTransport; production uses the default transport.
        self._mounts = {"all://": transport} if transport else None

    def _client(self) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(
            client_id=self._settings.google_client_id,
            client_secret=self._settings.google_client_secret.get_secret_value(),
            scope=SCOPE,
            redirect_uri=self._settings.google_redirect_uri,
            code_challenge_method="S256",
            timeout=10,
            mounts=self._mounts,
        )

    def authorization_url(self, state: str, code_verifier: str) -> str:
        url, _ = self._client().create_authorization_url(
            AUTHORIZE_URL, state=state, code_verifier=code_verifier, prompt="select_account"
        )
        return url

    async def fetch_user_info(self, code: str, code_verifier: str) -> GoogleUserInfo:
        try:
            async with self._client() as client:
                await client.fetch_token(TOKEN_URL, code=code, code_verifier=code_verifier)
                resp = await client.get(USERINFO_URL)
                resp.raise_for_status()
                return GoogleUserInfo.model_validate(resp.json())
        except (OAuthError, HTTPError, ValidationError, ValueError) as exc:
            raise GoogleOAuthError(type(exc).__name__) from exc


def get_google_client(settings: SettingsDep) -> GoogleOAuthClient:
    return GoogleOAuthClient(settings)


GoogleClientDep = Annotated[GoogleOAuthClient, Depends(get_google_client)]


def _reject(code: str, message: str) -> AppError:
    logger.info("google_login_rejected", extra={"fields": {"reason": code}})
    return AppError(403, code, message)


async def _unique_username(db: AsyncSession, email: str) -> str:
    """Username for a user created through Google: the email's local part, cleaned up,
    with a numeric suffix if taken. The user never types one in this flow."""
    base = re.sub(r"[^a-z0-9._-]", "", email.split("@", 1)[0].lower())[:40] or "user"
    base = base.ljust(3, "0")
    candidate, n = base, 1
    while await db.scalar(select(exists().where(User.username == candidate))):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


async def login_with_google(
    db: AsyncSession, info: GoogleUserInfo, invite_token: str | None, settings: Settings
) -> NewSession:
    if not info.email_verified:
        raise _reject("google_email_unverified", "Your Google email address is not verified")
    email = info.email.strip().lower()

    invite = None
    if invite_token:
        invite = await find_pending_invite_by_token(db, invite_token)
        if invite is None:
            raise _reject("invite_invalid", "This invite link is invalid or has expired")
        if invite.email.lower() != email:
            raise _reject(
                "invite_email_mismatch",
                "Sign in with the Google account for the invited email address",
            )

    user = await db.scalar(select(User).where(User.google_sub == info.sub))
    if user is None:
        user = await db.scalar(select(User).where(func.lower(User.email) == email))
        if user is not None and user.google_sub is not None:
            raise _reject(
                "google_account_conflict",
                "This account is already linked to a different Google account",
            )

    if user is not None:
        if not user.is_active:
            raise _reject("account_inactive", "This account has been deactivated")
        if user.google_sub is None:
            user.google_sub = info.sub
            logger.info("google_account_linked", extra={"fields": {"user_id": user.id}})
        logger.info("login_succeeded", extra={"fields": {"user_id": user.id, "method": "google"}})
        return await create_session(db, user, settings)

    if invite is None:
        invite = await find_pending_invite_by_email(db, email)
    if invite is None:
        raise _reject(
            "google_account_not_found", "No account or pending invite exists for this email"
        )
    user = await create_user_from_invite(
        db, invite, username=await _unique_username(db, email), google_sub=info.sub
    )
    return await create_session(db, user, settings)
