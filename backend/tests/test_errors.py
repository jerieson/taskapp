import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.core.middleware import _loggable_path
from tests.auth_helpers import fetch_csrf

pytestmark = pytest.mark.anyio


class Payload(BaseModel):
    title: str = Field(min_length=1)
    hours: float = Field(gt=0, le=24)


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    """The real app plus a few test-only routes."""

    @app.post("/api/_test/items")
    async def create_item(payload: Payload) -> Payload:
        return payload

    @app.get("/api/_test/conflict")
    async def conflict() -> None:
        raise AppError(409, "already_exists", "Already exists")

    @app.get("/api/_test/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    return app


async def test_unknown_api_route_returns_standard_404(client: AsyncClient) -> None:
    resp = await client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.json() == {"error": {"code": "not_found", "message": "Not Found"}}


async def test_method_not_allowed(client: AsyncClient) -> None:
    resp = await client.delete("/api/health")
    assert resp.status_code == 405
    assert resp.json()["error"]["code"] == "method_not_allowed"


async def test_validation_error_lists_fields(client: AsyncClient) -> None:
    await fetch_csrf(client)
    resp = await client.post("/api/_test/items", json={"title": "", "hours": 25})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Request validation failed"
    assert set(body["error"]["fields"]) == {"title", "hours"}


async def test_validation_error_for_missing_body(client: AsyncClient) -> None:
    await fetch_csrf(client)
    resp = await client.post("/api/_test/items")
    assert resp.status_code == 422
    assert "body" in resp.json()["error"]["fields"]


async def test_app_error(client: AsyncClient) -> None:
    resp = await client.get("/api/_test/conflict")
    assert resp.status_code == 409
    assert resp.json() == {"error": {"code": "already_exists", "message": "Already exists"}}


async def test_unhandled_exception_returns_generic_500(app: FastAPI) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/_test/boom")
    assert resp.status_code == 500
    assert resp.json() == {"error": {"code": "internal_error", "message": "Internal server error"}}
    assert "x-request-id" in resp.headers


async def test_request_id_generated_and_echoed(client: AsyncClient) -> None:
    resp = await client.get("/api/does-not-exist")
    assert len(resp.headers["x-request-id"]) == 32

    resp = await client.get("/api/does-not-exist", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["x-request-id"] == "abc-123"


async def test_invalid_request_id_is_replaced(client: AsyncClient) -> None:
    resp = await client.get("/api/does-not-exist", headers={"X-Request-ID": "bad id\n"})
    assert resp.headers["x-request-id"] != "bad id\n"


def test_logged_path_hides_path_param_values() -> None:
    scope = {"path": "/api/invites/s3cr3t-token", "path_params": {"token": "s3cr3t-token"}}
    assert _loggable_path(scope) == "/api/invites/{token}"
    assert _loggable_path({"path": "/api/health", "path_params": {}}) == "/api/health"
