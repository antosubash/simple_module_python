"""Task reads must not decode discarded payloads or window-count wide history."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution
from background_tasks.service import BackgroundTaskService
from simple_module_core.events import EventBus
from sqlalchemy import event


@pytest.fixture
def task_selects(engine):
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if (
            statement.lstrip().upper().startswith("SELECT")
            and "background_tasks_task_execution" in statement
        ):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    yield statements
    event.remove(engine.sync_engine, "before_cursor_execute", capture)


async def test_status_does_not_select_payload(seed_execution, authenticated_client, app):
    row = await seed_execution(result={"data": "x" * 1_000_000}, traceback="secret")
    statements = []
    engine = app.state.sm.db.engine

    def capture(conn, cursor, statement, parameters, context, executemany):
        if (
            statement.lstrip().upper().startswith("SELECT")
            and "background_tasks_task_execution" in statement
        ):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        response = await authenticated_client.get(
            f"/api/background_tasks/tasks/{row.celery_task_id}/status"
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert len(statements) == 1
    projection = statements[0].split("FROM")[0]
    for field in ("args", "kwargs", "result", "traceback"):
        assert f"background_tasks_task_execution.{field}" not in projection


@pytest.mark.parametrize(
    "page,expected_page,expected_args",
    [(1, 1, [0, 1]), (2, 2, [2, 3]), (99, 3, [4])],
)
async def test_list_projects_payload_and_counts_separately(
    db_session, task_selects, page, expected_page, expected_args
):
    now = datetime.now(UTC)
    rows = [
        TaskExecution(
            task_name="demo.task",
            status=TaskStatus.FAILED,
            tenant_id="acme",
            queued_at=now - timedelta(seconds=i) if i < 4 else None,
            args=[i],
            kwargs={"value": i},
            result={"data": "x" * 10000},
            traceback="secret",
        )
        for i in range(5)
    ]
    db_session.add_all(rows)
    db_session.add(TaskExecution(task_name="other", status=TaskStatus.SUCCESS))
    await db_session.flush()
    db_session.expunge_all()
    task_selects.clear()
    service = BackgroundTaskService(db_session, MagicMock(), EventBus())
    result = await service.list(
        status=TaskStatus.FAILED,
        task_name="demo",
        tenant_id="acme",
        queue="default",
        page=page,
        per_page=2,
    )
    assert (result.total, result.page, result.per_page) == (5, expected_page, 2)
    assert [(item.args, item.kwargs) for item in result.items] == [
        ([i], {"value": i}) for i in expected_args
    ]
    assert len(task_selects) == 2
    count, page = task_selects
    assert "count(" in count.lower() and "OVER" not in count
    assert "ORDER BY" not in count
    projection = page.split("FROM")[0]
    assert "count(" not in projection.lower()
    for field in ("result", "traceback"):
        assert f"background_tasks_task_execution.{field}" not in projection


@pytest.mark.parametrize("page", [0, 99])
async def test_empty_list_preserves_page_contract(db_session, page):
    service = BackgroundTaskService(db_session, MagicMock(), EventBus())
    result = await service.list(page=page)
    assert result.items == []
    assert result.total == 0
    assert result.page == max(1, page)
