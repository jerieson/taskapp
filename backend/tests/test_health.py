import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_session

pytestmark = pytest.mark.anyio


async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


async def test_health_db_down_returns_standard_error(app: FastAPI, client: AsyncClient) -> None:
    class BrokenSession:
        async def execute(self, *_: object) -> None:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    async def broken_session() -> BrokenSession:
        return BrokenSession()

    app.dependency_overrides[get_session] = broken_session
    resp = await client.get("/api/health")
    assert resp.status_code == 503
    assert resp.json() == {
        "error": {"code": "database_unavailable", "message": "Database is not reachable"}
    }
