"""Worker pool and startup timeouts (#531)."""

from types import SimpleNamespace

import pytest
from background_tasks import outbox_worker, sync_db
from background_tasks.db_settings import worker_database_options
from background_tasks.settings import BackgroundTasksSettings
from simple_module_test.database import database_url_for_tests
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError


def options(**changes):
    host = SimpleNamespace(
        db_pool_timeout=17,
        db_connect_timeout=4,
        db_statement_timeout_ms=1000,
        db_idle_in_tx_timeout_ms=2000,
    )
    return worker_database_options(host, BackgroundTasksSettings(**changes))


@pytest.fixture(autouse=True)
def cleanup():
    yield
    outbox_worker.reset_worker_state()
    sync_db.dispose_sync_engine()


def test_worker_env(monkeypatch):
    monkeypatch.setenv("SM_BG_TASKS_DB_POOL_SIZE", "4")
    monkeypatch.setenv("SM_BG_TASKS_DB_MAX_OVERFLOW", "5")
    monkeypatch.setenv("SM_BG_TASKS_DB_RECYCLE", "90")
    monkeypatch.setenv("SM_BG_TASKS_DB_STATEMENT_TIMEOUT_MS", "0")
    result = options()
    assert result == {
        "pool_size": 4,
        "max_overflow": 5,
        "pool_recycle": 90,
        "pool_timeout": 17,
        "connect_timeout": 4,
        "statement_timeout_ms": 0,
        "idle_in_tx_timeout_ms": 2000,
    }


def test_sync_options():
    sync_db.set_database_url("postgresql+asyncpg://localhost/db")
    sync_db.configure_database(options())
    engine = sync_db.get_sync_session_factory().kw["bind"]
    assert engine.pool.timeout() == 17
    assert engine.pool.size() == 2
    captured = {}

    @event.listens_for(engine, "do_connect")
    def capture(dialect, record, args, kwargs):
        captured.update(kwargs)
        raise RuntimeError("captured")

    with pytest.raises(RuntimeError, match="captured"):
        engine.connect()
    assert captured["connect_timeout"] == 4
    assert captured["options"] == (
        "-c statement_timeout=1000 -c idle_in_transaction_session_timeout=2000"
    )


async def test_outbox_options(monkeypatch):
    sync_db.set_database_url("sqlite+aiosqlite://")
    sync_db.configure_database(options())
    captured = {}
    cache = {}
    monkeypatch.setattr(outbox_worker, "worker_loop_cache", lambda: cache)
    original = outbox_worker.init_db

    def capture(url, **kwargs):
        captured.update(kwargs)
        return original(url, **kwargs)

    monkeypatch.setattr(outbox_worker, "init_db", capture)
    outbox_worker.worker_session_factory()
    assert captured == options()
    await outbox_worker._dispose_cached(cache)


@pytest.mark.postgres
def test_worker_statement_timeout():
    sync_db.set_database_url(database_url_for_tests())
    sync_db.configure_database(options())
    with (
        sync_db.get_sync_session_factory()() as session,
        pytest.raises(DBAPIError, match="statement timeout"),
    ):
        session.execute(text("SELECT pg_sleep(2)"))
