"""Per-request SQL statement counting (feeds the dev Server-Timing header)."""

from __future__ import annotations

import asyncio

from simple_module_db.query_stats import install_query_stats, track_queries
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def test_counts_only_statements_inside_the_tracked_block() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    install_query_stats(engine)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))  # untracked
            with track_queries() as stats:
                await conn.execute(text("select 1"))
                await conn.execute(text("select 2"))
            await conn.execute(text("select 3"))  # after the block
        assert stats.count == 2
        assert stats.seconds > 0
    finally:
        await engine.dispose()


async def test_install_is_idempotent() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    install_query_stats(engine)
    install_query_stats(engine)
    try:
        with track_queries() as stats:
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
        # A second install must not register the listeners twice.
        assert stats.count == 1
    finally:
        await engine.dispose()


async def test_child_tasks_share_the_request_totals() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    install_query_stats(engine)

    async def one_query() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))

    try:
        with track_queries() as stats:
            await asyncio.gather(one_query(), one_query())
        assert stats.count == 2
    finally:
        await engine.dispose()


async def test_engine_without_install_counts_nothing() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        with track_queries() as stats:
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
        assert stats.count == 0
    finally:
        await engine.dispose()
