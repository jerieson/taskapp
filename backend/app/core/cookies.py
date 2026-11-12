"""Auth cookies.

- `session`: the session token. httpOnly, so JavaScript can never read it.
- `csrf_token`: readable by JavaScript, which echoes it in the X-CSRF-Token header
  (double-submit). Once logged in it equals the session's stored csrf_token.

Both are SameSite=Lax; Secure comes from COOKIE_SECURE.
"""

from starlette.responses import Response

from app.core.config import Settings

SESSION_COOKIE = "session"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def set_session_cookies(
    response: Response, settings: Settings, session_token: str, csrf_token: str
) -> None:
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=max_age,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    set_csrf_cookie(response, settings, csrf_token, max_age=max_age)


def set_csrf_cookie(
    response: Response, settings: Settings, csrf_token: str, max_age: int | None = None
) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age if max_age is not None else settings.session_ttl_hours * 3600,
        path="/",
        secure=settings.cookie_secure,
        httponly=False,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
    )
