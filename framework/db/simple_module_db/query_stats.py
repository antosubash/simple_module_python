"""Per-request SQL statement counting.

Development hosts install this on their engine and expose the totals in a
``Server-Timing`` header (see ``simple_module_hosting._server_timing``), so a
page that issues one query per row shows up in the browser's network panel and
in the page-perf audit instead of only under load.

Counting is opt-in twice over: :func:`install_query_stats` adds the engine
listeners, and only code inside :func:`track_queries` is counted. Statements
run outside a tracked block (startup, background work) cost one ContextVar
read each.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

__all__ = ["QueryStats", "install_query_stats", "track_queries"]

_START_KEY = "_sm_query_started"
_INSTALLED_FLAG = "_sm_query_stats_installed"


@dataclass(slots=True)
class QueryStats:
    """Statements executed inside one :func:`track_queries` block."""

    count: int = 0
    seconds: float = 0.0


_current: ContextVar[QueryStats | None] = ContextVar("sm_query_stats", default=None)


def _before(conn, cursor, statement, parameters, context, executemany) -> None:
    if _current.get() is not None and context is not None:
        setattr(context, _START_KEY, time.perf_counter())


def _after(conn, cursor, statement, parameters, context, executemany) -> None:
    stats = _current.get()
    if stats is None:
        return
    stats.count += 1
    started = getattr(context, _START_KEY, None) if context is not None else None
    if started is not None:
        stats.seconds += time.perf_counter() - started


def install_query_stats(engine: AsyncEngine) -> None:
    """Count statements on *engine* for any :func:`track_queries` block.

    Idempotent per engine.
    """
    sync_engine = engine.sync_engine
    if getattr(sync_engine, _INSTALLED_FLAG, False):
        return
    event.listen(sync_engine, "before_cursor_execute", _before)
    event.listen(sync_engine, "after_cursor_execute", _after)
    setattr(sync_engine, _INSTALLED_FLAG, True)


@contextmanager
def track_queries() -> Generator[QueryStats]:
    """Count the statements run by this task (and tasks it spawns) until exit.

    The stats object is shared by reference, so work SQLAlchemy runs in a
    greenlet or a child task still lands in the same totals.
    """
    stats = QueryStats()
    token = _current.set(stats)
    try:
        yield stats
    finally:
        _current.reset(token)
