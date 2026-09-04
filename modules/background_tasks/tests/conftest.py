"""Shared fixtures for background_tasks tests."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from background_tasks import sync_db
from background_tasks.constants import PERM_VIEW, TaskStatus
from background_tasks.models import TaskExecution
from sqlalchemy import select


@pytest.fixture
async def _stub_celery(app) -> None:
    """Replace the real Celery instance with a MagicMock.

    Opt-in via ``pytestmark = pytest.mark.usefixtures("_stub_celery")`` at
    module scope — not autouse, because signal tests deliberately exercise
    an unstarted app and would be broken by the implicit ``app`` dependency.
    ``send_task.return_value.id`` is pre-set so retry flows that read it
    (see ``test_admin_api.py``) work without further setup.
    """
    celery = MagicMock(name="Celery")
    celery.send_task.return_value.id = "mocked-celery-id"
    app.state.background_tasks.celery = celery


@pytest.fixture
def sync_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point ``sync_db`` at a fresh on-disk SQLite file and reset the cache.

    Shared between the signal-handler suite and the stuck-sweep suite; both
    exercise the sync DB code path that workers use, and need a clean engine
    per test so the process-global cache doesn't bleed across files.

    Uses ``dispose_sync_engine`` for setup and teardown — it's the only sweep
    that also clears ``_url_override``, so a prior call to
    ``set_database_url(...)`` in some other test (or worker module startup)
    can't shadow the ``SM_DATABASE_URL`` we set here.
    """
    db_file = tmp_path / "bg_tasks_sync.db"
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite:///{db_file}")
    sync_db.dispose_sync_engine()

    factory = sync_db.get_sync_session_factory()
    TaskExecution.metadata.create_all(factory.kw["bind"])

    yield db_file

    sync_db.dispose_sync_engine()


@pytest.fixture
def seed_execution(app):
    """Insert one ``TaskExecution`` and hand it back.

    A factory rather than a fixture value: nearly every test in the retry
    suites needs several rows that differ in one field, and spelling the whole
    constructor out each time buries the one thing the test is about.
    """

    async def _seed(
        *,
        task_name: str = "demo.task",
        status: TaskStatus = TaskStatus.FAILED,
        queue: str = "default",
        queued_at: datetime | None = None,
    ) -> TaskExecution:
        row = TaskExecution(
            celery_task_id=str(uuid.uuid4()),
            task_name=task_name,
            status=status,
            queue=queue,
            args=[],
            kwargs={},
            queued_at=queued_at or datetime.now(UTC),
        )
        async with app.state.sm.db.session_factory() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return row

    return _seed


@pytest.fixture
def execution_rows(app):
    """Every ``TaskExecution`` currently in the database, read fresh."""

    async def _rows() -> list[TaskExecution]:
        async with app.state.sm.db.session_factory() as session:
            return list((await session.execute(select(TaskExecution))).scalars())

    return _rows


@pytest.fixture
def view_only(app) -> None:
    """Downgrade the seeded admin to ``background_tasks.view`` for one test.

    The admin role carries the wildcard, so nothing else in this suite can tell
    a ``view`` gate from a ``manage`` gate — every endpoint would pass either
    way. Pinning the registry's resolved role map is the smallest way to get a
    principal genuinely allowed to read the executions table and genuinely not
    allowed to sweep it.
    """
    app.state.sm.permissions._role_map_cache = {"admin": [PERM_VIEW]}
