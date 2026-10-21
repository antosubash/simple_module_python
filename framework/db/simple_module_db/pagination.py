"""Offset pagination: one place that clamps, counts and slices.

``PageParams`` is a plain value (no FastAPI import, so the DB package stays
web-free); ``simple_module_hosting.pagination`` builds it from query strings.
``paginate`` counts the *same statement* as a subquery, so soft-delete and
tenant filters apply to the count exactly as they do to the rows.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlmodel import SQLModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import Select


DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 200


def total_pages(total: int, per_page: int) -> int:
    """Number of pages for ``total`` rows; always at least 1 (an empty list is page 1)."""
    return max(1, math.ceil(max(total, 0) / max(per_page, 1)))


def clamp_page(page: int, total: int, per_page: int) -> int:
    """``page`` limited to ``1..total_pages`` so a stale link lands on the last real page."""
    return min(max(page, 1), total_pages(total, per_page))


@dataclass(frozen=True, slots=True)
class PageParams:
    """A requested page. Values are normalised on construction, never trusted."""

    page: int = 1
    per_page: int = DEFAULT_PER_PAGE

    def __post_init__(self) -> None:
        object.__setattr__(self, "page", max(int(self.page), 1))
        object.__setattr__(self, "per_page", max(1, min(int(self.per_page), MAX_PER_PAGE)))

    @property
    def offset(self) -> int:
        """SQL OFFSET for the requested page; never negative."""
        return (self.page - 1) * self.per_page


class Page[T](SQLModel):
    """One page of results. ``page`` is the page actually served (after clamping)."""

    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int


async def paginate(
    session: AsyncSession,
    stmt: Select[Any],
    params: PageParams,
    *,
    scalars: bool = True,
) -> Page[Any]:
    """Run ``stmt`` one page at a time.

    ``stmt`` must carry its own ``ORDER BY``. A page past the end is clamped to
    the last page, so the client never gets an empty list with a non-zero
    total. ``scalars=False`` returns row objects for multi-column selects.
    """
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int((await session.execute(count_stmt)).scalar_one())
    page = clamp_page(params.page, total, params.per_page)
    paged = stmt.offset((page - 1) * params.per_page).limit(params.per_page)
    result = await session.execute(paged)
    items = list(result.scalars().all() if scalars else result.all())
    return Page(
        items=items,
        total=total,
        page=page,
        per_page=params.per_page,
        pages=total_pages(total, params.per_page),
    )
