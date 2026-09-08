"""Shared helpers for the file_storage suite.

``recorded_statements`` is the tool the performance tests are written with:
this module's cost problem is *how many* queries a screen issues, not how long
they take, so the assertions count statements rather than milliseconds. A
wall-clock budget would be the flakiest check in CI and would still pass on the
day someone adds a fourth full-table scan to a fast machine.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine


@pytest.fixture
def record_statements():
    """Yield a context manager recording SQL issued against an engine.

    Takes the app or engine to watch and returns a growing list of normalised
    statement texts, so a test can filter for the ones naming a table it cares
    about.
    """

    @contextlib.contextmanager
    def _watch(target) -> Iterator[list[str]]:
        engine = _sync_engine(target)
        seen: list[str] = []

        def _record(conn, cursor, statement, parameters, context, executemany) -> None:
            seen.append(" ".join(statement.split()))

        event.listen(engine, "before_cursor_execute", _record)
        try:
            yield seen
        finally:
            event.remove(engine, "before_cursor_execute", _record)

    return _watch


def _sync_engine(target) -> Engine:
    """Accept an app, an ``AsyncEngine`` or a sync ``Engine`` interchangeably."""
    engine = target.state.sm.db.engine if hasattr(target, "state") else target
    return getattr(engine, "sync_engine", engine)
