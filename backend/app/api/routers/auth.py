from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.core.config import SettingsDep
from app.core.cookies import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    clear_session_cookie,
    set_csrf_cookie,
    set_session_cookies,
)
from app.core.dependencies import CurrentAuth, CurrentUser
from app.core.errors import AppError
from app.core.rate_limit import LoginLimiterDep, client_ip
from app.core.security import generate_token, sign_value, tokens_equal, unsign_value
from app.db.session import SessionDep
from app.schemas.auth import ChangePasswordIn, CsrfOut, LoginIn, MeOut
from app.services import auth as auth_service
from app.services.google import GoogleClientDep, GoogleOAuthError, login_with_google
from app.services.users import to_me

router = APIRouter(prefix="/auth", tags=["auth"])

OAUTH_STATE_COOKIE = "oauth_state"
OAUTH_STATE_PATH = "/api/auth/google"
OAUTH_STATE_MAX_AGE = 600


@router.get("/csrf", response_model=CsrfOut)
async def csrf(request: Request, response: Response, settings: SettingsDep) -> CsrfOut:
    """Issue (or return) the csrf_token cookie. Public.

    Call before the first non-GET request when no csrf_token cookie exists yet
    (e.g. before logging in). Logged-in clients already have one.
    """
    token = request.cookies.get(CSRF_COOKIE) or generate_token()
    set_csrf_cookie(response, settings, token)
    return CsrfOut(csrf_token=token)


@router.post("/login", response_model=MeOut)
async def login(
    data: LoginIn,
    request: Request,
    response: Response,
    db: SessionDep,
    settings: SettingsDep,
    limiter: LoginLimiterDep,
) -> MeOut:
    ip = client_ip(request, settings)
    limiter.check(ip)
    new = await auth_service.login(db, data.username, data.password, settings)
    if new is None:
        limiter.record_failure(ip)
        raise AppError(401, "invalid_credentials", "Invalid username or password")
    # Logging in replaces whatever session this browser had.
    previous = await auth_service.get_auth_context(db, request.cookies.get(SESSION_COOKIE))
    if previous is not None and previous.session.id != new.session.id:
        await auth_service.revoke_session(db, previous.session)
    set_session_cookies(response, settings, new.token, new.csrf_token)
    return await to_me(db, new.user)


@router.post("/logout", status_code=204)
async def logout(
    ctx: CurrentAuth, response: Response, db: SessionDep, settings: SettingsDep
) -> None:
    await auth_service.revoke_session(db, ctx.session)
    clear_session_cookie(response, settings)
    # Fresh pre-session token so the login form works without another round trip.
    set_csrf_cookie(response, settings, generate_token())


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser, db: SessionDep) -> MeOut:
    return await to_me(db, user)


@router.post("/change-password", status_code=204)
async def change_password(data: ChangePasswordIn, ctx: CurrentAuth, db: SessionDep) -> None:
    """Requires the current password. Every other session of the user is revoked."""
    await auth_service.change_password(db, ctx, data.current_password, data.new_password)


def _frontend_redirect(
    settings: SettingsDep, path: str, error: str | None = None
) -> RedirectResponse:
    query = f"?{urlencode({'error': error})}" if error else ""
    return RedirectResponse(f"{settings.frontend_url}{path}{query}", status_code=302)


@router.get("/google/login", status_code=302, response_class=RedirectResponse)
async def google_login(
    settings: SettingsDep,
    google: GoogleClientDep,
    invite: Annotated[str | None, Query(max_length=128)] = None,
) -> RedirectResponse:
    """Redirect to Google. Public. `invite` carries an invite token when the user
    accepts an invite with Google."""
    if not settings.google_enabled:
        return _frontend_redirect(settings, "/login", "google_not_configured")
    state, verifier = generate_token(), generate_token()
    response = RedirectResponse(google.authorization_url(state, verifier), status_code=302)
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        sign_value(
            settings.secret_key.get_secret_value(),
            {"state": state, "verifier": verifier, "invite": invite},
            OAUTH_STATE_MAX_AGE,
        ),
        max_age=OAUTH_STATE_MAX_AGE,
        path=OAUTH_STATE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/google/callback", status_code=302, response_class=RedirectResponse)
async def google_callback(
    request: Request,
    db: SessionDep,
    settings: SettingsDep,
    google: GoogleClientDep,
    code: Annotated[str | None, Query(max_length=2048)] = None,
    state: Annotated[str | None, Query(max_length=256)] = None,
    error: Annotated[str | None, Query(max_length=256)] = None,
) -> RedirectResponse:
    """Google redirects here. Public. Ends with a redirect to the frontend: `/` on
    success, `/login?error=<code>` on failure."""
    saved = unsign_value(
        settings.secret_key.get_secret_value(), request.cookies.get(OAUTH_STATE_COOKIE)
    )
    response: RedirectResponse
    if not settings.google_enabled:
        response = _frontend_redirect(settings, "/login", "google_not_configured")
    elif saved is None or not state or not tokens_equal(saved.get("state"), state):
        response = _frontend_redirect(settings, "/login", "google_state_invalid")
    elif error or not code:
        response = _frontend_redirect(settings, "/login", "google_cancelled")
    else:
        try:
            info = await google.fetch_user_info(code, str(saved["verifier"]))
            new = await login_with_google(db, info, saved.get("invite"), settings)
        except GoogleOAuthError:
            response = _frontend_redirect(settings, "/login", "google_failed")
        except AppError as exc:
            response = _frontend_redirect(settings, "/login", exc.code)
        else:
            response = _frontend_redirect(settings, "/")
            set_session_cookies(response, settings, new.token, new.csrf_token)
    response.delete_cookie(OAUTH_STATE_COOKIE, path=OAUTH_STATE_PATH)
    return response
