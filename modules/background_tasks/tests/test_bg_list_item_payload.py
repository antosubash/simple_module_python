"""The listing rows carry the task payload.

The retry confirm opens straight from a row in the executions table, and it has
to show what it is about to re-enqueue — re-running a payload that is itself the
reason the task failed just fails the same way. The list schema deliberately
carries ``args``/``kwargs`` for that one consumer, so these tests pin them
against a future "trim the list DTO" tidy-up.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from background_tasks.constants import TaskStatus
from background_tasks.contracts.schemas import TaskExecutionListItem
from background_tasks.models import TaskExecution

VIEW_BASE = "/admin/background-tasks/"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}

pytestmark = pytest.mark.usefixtures("_stub_celery")

_ARGS = ["dana@acme.com", 42]
_KWARGS = {"template": "invite", "retry": False}


async def _seed(app) -> None:
    """Commit through the app's own session factory — a row flushed on the test
    session is invisible to the request handler's session."""
    row = TaskExecution(
        task_name="users.send_invite",
        status=TaskStatus.FAILED,
        queue="default",
        args=_ARGS,
        kwargs=_KWARGS,
        queued_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    async with app.state.sm.db.session_factory() as session:
        session.add(row)
        await session.commit()


class TestListItemSchema:
    def test_declares_the_payload_fields(self) -> None:
        assert {"args", "kwargs"} <= set(TaskExecutionListItem.model_fields)

    def test_defaults_are_empty_not_none(self) -> None:
        """The page spreads these straight into a component; ``None`` would
        turn a missing payload into a render crash rather than "no arguments"."""
        item = TaskExecutionListItem(
            id="00000000-0000-0000-0000-000000000001",
            task_name="noop",
            status=TaskStatus.PENDING,
            queue="default",
            retries=0,
        )
        assert item.args == []
        assert item.kwargs == {}


class TestIndexViewExposesThePayload:
    async def test_row_carries_args_and_kwargs(
        self,
        app,
        authenticated_client: httpx.AsyncClient,
    ) -> None:
        await _seed(app)

        resp = await authenticated_client.get(VIEW_BASE, headers=INERTIA_HEADERS)
        assert resp.status_code == 200
        rows = resp.json()["props"]["executions"]

        assert len(rows) == 1
        assert rows[0]["args"] == _ARGS
        assert rows[0]["kwargs"] == _KWARGS
