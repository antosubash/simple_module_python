"""Bulk retry: what must not happen twice, and in what order it happens.

Scope lives in ``test_retry_failed_bulk.py`` and the per-press guards in
``test_retry_failed_guards.py``. This file covers the three properties that
keep two simultaneous presses from running every task twice:

* the claim locks the batch it takes, so a second sweep cannot read it;
* the rows recording the attempts are written *before* anything is published;
* the retry is announced only once those rows are durable.

**What each test actually proves.** The suite runs on SQLite, where
``FOR UPDATE SKIP LOCKED`` is a no-op — a two-task race here would pass with
the locking removed and prove nothing. So the lock is asserted on the *SQL the
claim compiles to* against the Postgres dialect, which is where the clause has
to be right; the other two are ordering invariants observable on any backend,
and they are what makes a lost race cheap rather than catastrophic.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from background_tasks.constants import RETRY_ALL_BATCH, TABLE_TASK_EXECUTION, TaskStatus
from background_tasks.contracts.events import TaskRetried
from background_tasks.filters import bulk_retry_conditions
from background_tasks.retry_service import claim_query
from sqlalchemy import event
from sqlalchemy.dialects import postgresql

ADMIN_BASE = "/api/background_tasks/admin"
RETRY_FAILED = f"{ADMIN_BASE}/executions/retry-failed"


def _compiled_claim() -> str:
    conditions = bulk_retry_conditions()
    assert conditions is not None
    return str(claim_query(conditions, RETRY_ALL_BATCH).compile(dialect=postgresql.dialect()))


class TestTheClaimLocksItsBatch:
    """Asserted on the emitted SQL, not on behaviour.

    SQLite has no row locks and SQLAlchemy silently drops the clause there, so
    running two sweeps against the test database would pass either way. The
    compiled Postgres statement is the only thing in reach of this suite that
    can tell the fix from its absence.
    """

    def test_the_claim_takes_a_row_lock(self) -> None:
        assert "FOR UPDATE" in _compiled_claim()

    def test_a_second_sweep_skips_a_held_row_rather_than_waiting_for_it(self) -> None:
        """``SKIP LOCKED``: the second operator gets an answer, not a queue."""
        assert "SKIP LOCKED" in _compiled_claim()

    def test_the_claim_is_still_the_oldest_rows_first(self) -> None:
        """Locking must not have cost the ordering the sweep is defined by."""
        sql = _compiled_claim()
        assert "ORDER BY" in sql
        assert sql.index("ORDER BY") < sql.index("LIMIT") < sql.index("FOR UPDATE")


@pytest.fixture
def sweep_trace(app) -> Iterator[list[str]]:
    """Every insert, commit and broker publish this sweep makes, in order.

    Recorded at the engine and at the Celery stub rather than inside the
    coordinator, so the test asserts on what the database and the broker
    actually saw and not on the shape of the code that talked to them.
    """
    trace: list[str] = []
    engine = app.state.sm.db.engine.sync_engine

    def _record_statement(conn, cursor, statement, parameters, context, executemany) -> None:
        if statement.lstrip().lower().startswith(f"insert into {TABLE_TASK_EXECUTION}"):
            trace.append("insert")

    def _record_commit(conn) -> None:
        trace.append("commit")

    def _send_task(name: str, **options: Any) -> MagicMock:
        trace.append("publish")
        result = MagicMock()
        result.id = options.get("task_id", "mocked-celery-id")
        return result

    celery = MagicMock(name="Celery")
    celery.send_task.side_effect = _send_task
    app.state.background_tasks.celery = celery

    event.listen(engine, "before_cursor_execute", _record_statement)
    event.listen(engine, "commit", _record_commit)
    try:
        yield trace
    finally:
        event.remove(engine, "before_cursor_execute", _record_statement)
        event.remove(engine, "commit", _record_commit)


class TestRowsBeforeBroker:
    """The row recording an attempt exists before the attempt is sent.

    Provable on any backend. It is what makes losing the race survivable: an
    orphaned ``pending`` row nobody sent is a row an operator can see and retry,
    while a task published against no row has already run twice by the time
    anyone notices.
    """

    async def test_the_retry_row_is_written_before_the_task_is_published(
        self, sweep_trace, seed_execution, authenticated_client: httpx.AsyncClient
    ) -> None:
        await seed_execution(status=TaskStatus.FAILED)
        sweep_trace.clear()  # Drop the seed's own insert and commit.

        resp = await authenticated_client.post(RETRY_FAILED)

        assert resp.json() == {"queued": 1, "remaining": 0}
        assert sweep_trace.index("insert") < sweep_trace.index("publish")

    async def test_the_whole_batch_lands_before_the_first_publish(
        self, sweep_trace, seed_execution, authenticated_client: httpx.AsyncClient
    ) -> None:
        """One flush for the batch, and it is complete before anything is sent."""
        for i in range(3):
            await seed_execution(task_name=f"task.{i}", status=TaskStatus.FAILED)
        sweep_trace.clear()

        resp = await authenticated_client.post(RETRY_FAILED)

        assert resp.json() == {"queued": 3, "remaining": 0}
        first_publish = sweep_trace.index("publish")
        assert sweep_trace.count("publish") == 3
        assert sweep_trace[:first_publish].count("insert") >= 1
        assert "insert" not in sweep_trace[first_publish:]

    async def test_the_row_names_the_task_that_was_actually_sent(
        self,
        app,
        sweep_trace,
        seed_execution,
        execution_rows,
        authenticated_client: httpx.AsyncClient,
    ) -> None:
        """Writing first means reserving the broker id, not inventing one later.

        If the reserved id and the published id could differ, an orphaned row
        would be unmatchable against the broker and writing first would buy
        nothing.
        """
        original = await seed_execution(status=TaskStatus.FAILED)

        await authenticated_client.post(RETRY_FAILED)

        new_row = next(r for r in await execution_rows() if r.id != original.id)
        sent = app.state.background_tasks.celery.send_task.call_args
        assert new_row.celery_task_id == sent.kwargs["task_id"]


class TestAnnouncedAfterCommit:
    """Subscribers hear about a retry that happened, not one that might.

    Publishing inline told them about an uncommitted transaction — and for a
    500-row sweep, told them nothing until the batch was done and then
    everything at once, for work that could still roll back.
    """

    async def test_the_event_fires_after_the_rows_are_committed(
        self, app, sweep_trace, seed_execution, authenticated_client: httpx.AsyncClient
    ) -> None:
        async def _on_retried(event_: TaskRetried) -> None:
            sweep_trace.append("announced")

        app.state.sm.event_bus.subscribe(TaskRetried, _on_retried)
        await seed_execution(status=TaskStatus.FAILED)
        sweep_trace.clear()

        await authenticated_client.post(RETRY_FAILED)

        assert "announced" in sweep_trace
        assert sweep_trace.index("commit") < sweep_trace.index("announced")

    async def test_one_event_per_retried_row(
        self, app, sweep_trace, seed_execution, authenticated_client: httpx.AsyncClient
    ) -> None:
        received: list[TaskRetried] = []

        async def _on_retried(event_: TaskRetried) -> None:
            received.append(event_)

        app.state.sm.event_bus.subscribe(TaskRetried, _on_retried)
        for i in range(3):
            await seed_execution(task_name=f"task.{i}", status=TaskStatus.FAILED)

        await authenticated_client.post(RETRY_FAILED)

        assert sorted(e.task_name for e in received) == ["task.0", "task.1", "task.2"]
