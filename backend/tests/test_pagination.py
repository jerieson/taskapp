import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination, PaginationParams, paginate

pytestmark = pytest.mark.anyio


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    @app.get("/api/_test/numbers", response_model=Page[int])
    async def numbers(params: Pagination) -> Page[int]:
        data = list(range(120))
        window = data[params.offset : params.offset + params.limit]
        return Page.build(window, len(data), params)

    return app


async def test_defaults(client: AsyncClient) -> None:
    resp = await client.get("/api/_test/numbers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert body["total"] == 120
    assert body["items"] == list(range(50))


async def test_limit_and_offset(client: AsyncClient) -> None:
    resp = await client.get("/api/_test/numbers", params={"limit": 10, "offset": 115})
    assert resp.json()["items"] == list(range(115, 120))


@pytest.mark.parametrize(
    ("params", "field"),
    [({"limit": 201}, "limit"), ({"limit": 0}, "limit"), ({"offset": -1}, "offset")],
)
async def test_out_of_range_params_rejected(
    client: AsyncClient, params: dict[str, int], field: str
) -> None:
    resp = await client.get("/api/_test/numbers", params=params)
    assert resp.status_code == 422
    assert field in resp.json()["error"]["fields"]


async def test_paginate_against_database(db: AsyncSession) -> None:
    series = func.generate_series(1, 120).table_valued("value").render_derived()
    stmt = select(series.c.value).order_by(series.c.value)
    items, total = await paginate(db, stmt, PaginationParams(limit=5, offset=100))
    assert total == 120
    assert list(items) == [101, 102, 103, 104, 105]
