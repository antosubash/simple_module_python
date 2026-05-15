"""Shared fixtures for background_tasks tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from background_tasks import sync_db
from background_tasks.models import TaskExecution


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
