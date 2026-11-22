"""paginate / PageParams: clamping, counting through filters, no negative offset."""

from __future__ import annotations

import pytest
from simple_module_db import PageParams, clamp_page, paginate, total_pages
from sqlmodel import Field, SQLModel, select


class _Item(SQLModel, table=True):
    __tablename__ = "pagination_test_item"
    __table_args__ = {"extend_existing": True}
    id: int | None = Field(default=None, primary_key=True)
    n: int = 0


def test_params_never_negative_offset():
    assert PageParams(page=0).offset == 0
    assert PageParams(page=-5, per_page=10).offset == 0
    assert PageParams(page=3, per_page=10).offset == 20


def test_params_clamp_per_page():
    assert PageParams(per_page=0).per_page == 1
    assert PageParams(per_page=10_000).per_page == 200


def test_total_pages_and_clamp():
    assert total_pages(0, 10) == 1
    assert total_pages(21, 10) == 3
    assert clamp_page(99, 21, 10) == 3
    assert clamp_page(0, 21, 10) == 1


@pytest.fixture
async def seeded(db_session):
    from sqlalchemy import text  # noqa: F401

    conn = await db_session.connection()
    await conn.run_sync(lambda c: _Item.__table__.create(c, checkfirst=True))
    db_session.add_all([_Item(n=i) for i in range(23)])
    await db_session.flush()
    return db_session


async def test_paginate_slices_and_counts(seeded):
    stmt = select(_Item).order_by(_Item.n)
    page = await paginate(seeded, stmt, PageParams(page=2, per_page=10))
    assert (page.total, page.page, page.pages, page.per_page) == (23, 2, 3, 10)
    assert [i.n for i in page.items] == list(range(10, 20))


async def test_paginate_clamps_past_the_end(seeded):
    stmt = select(_Item).order_by(_Item.n)
    page = await paginate(seeded, stmt, PageParams(page=50, per_page=10))
    assert page.page == 3
    assert [i.n for i in page.items] == [20, 21, 22]


async def test_paginate_count_follows_filters(seeded):
    stmt = select(_Item).where(_Item.n < 5).order_by(_Item.n)
    page = await paginate(seeded, stmt, PageParams(per_page=2))
    assert (page.total, page.pages, len(page.items)) == (5, 3, 2)


async def test_paginate_empty(seeded):
    stmt = select(_Item).where(_Item.n > 1000).order_by(_Item.n)
    page = await paginate(seeded, stmt, PageParams(page=4))
    assert (page.total, page.page, page.pages, page.items) == (0, 1, 1, [])


async def test_paginate_rows(seeded):
    stmt = select(_Item.n).order_by(_Item.n)
    page = await paginate(seeded, stmt, PageParams(per_page=3), scalars=False)
    assert [r.n for r in page.items] == [0, 1, 2]
