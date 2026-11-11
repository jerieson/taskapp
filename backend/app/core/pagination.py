"""Shared pagination for every list endpoint.

Usage in a router:

    @router.get("", response_model=Page[TaskOut])
    async def list_tasks(params: Pagination, session: SessionDep) -> Page[TaskOut]:
        items, total = await paginate(session, stmt, params)
        return Page.build(items, total, params)
"""

from collections.abc import Sequence
from typing import Annotated, Any, Self

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class PaginationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    offset: int = Field(0, ge=0)


Pagination = Annotated[PaginationParams, Query()]


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int

    @classmethod
    def build(cls, items: Sequence[Any], total: int, params: PaginationParams) -> Self:
        return cls.model_validate(
            {"items": list(items), "total": total, "limit": params.limit, "offset": params.offset},
            from_attributes=True,
        )


async def paginate[R](
    session: AsyncSession, stmt: Select[tuple[R]], params: PaginationParams
) -> tuple[Sequence[R], int]:
    """Run `stmt` with limit/offset and return (items, total count)."""
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await session.execute(count_stmt)).scalar_one()
    result = await session.scalars(stmt.limit(params.limit).offset(params.offset))
    return result.all(), total
