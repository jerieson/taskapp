"""Helpers for logging test clients in."""

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Role, User
from app.services.auth import create_session
from tests.factories import make_user

PASSWORD = "correct-horse-1"
CSRF_HEADER = "X-CSRF-Token"


async def fetch_csrf(client: AsyncClient) -> str:
    """Get the pre-session CSRF cookie and send it as a header from now on."""
    resp = await client.get("/api/auth/csrf")
    assert resp.status_code == 200
    token = resp.json()["csrf_token"]
    client.headers[CSRF_HEADER] = token
    return token


def sync_csrf_header(client: AsyncClient) -> None:
    """Copy the current csrf_token cookie into the header (as the frontend does)."""
    client.headers[CSRF_HEADER] = client.cookies["csrf_token"]


async def login(client: AsyncClient, username: str, password: str = PASSWORD) -> Response:
    if "csrf_token" not in client.cookies:
        await fetch_csrf(client)
    resp = await client.post("/api/auth/login", json={"username": username, "password": password})
    sync_csrf_header(client)
    return resp


async def login_as(
    client: AsyncClient, db: AsyncSession, role: Role = Role.DEV, **kw: object
) -> User:
    """Create a user with PASSWORD and log `client` in as them."""
    user = await make_user(db, role=role, password=PASSWORD, **kw)
    resp = await login(client, user.username)
    assert resp.status_code == 200, resp.text
    return user


async def use_new_session(client: AsyncClient, db: AsyncSession, user: User) -> None:
    """Log `client` in as `user` without a password (e.g. Google-only users)."""
    new = await create_session(db, user, get_settings())
    client.cookies.set("session", new.token)
    client.cookies.set("csrf_token", new.csrf_token)
    client.headers[CSRF_HEADER] = new.csrf_token
