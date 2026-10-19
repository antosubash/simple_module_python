"""The cached sync engine must not survive a fork (#532).

A prefork Celery child inherits the parent's module globals — including pooled
sockets. Two processes on one Postgres connection interleave protocol frames.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from background_tasks import sync_db
from sqlalchemy import text


@pytest.fixture(autouse=True)
def _reset_sync_db() -> Iterator[None]:
    sync_db.dispose_sync_engine()
    yield
    sync_db.dispose_sync_engine()


def test_pid_change_rebuilds_engine_without_closing_inherited_sockets(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sync_db.set_database_url(f"sqlite:///{tmp_path / 'a.db'}")
    sync_db.get_sync_session_factory()
    parent = sync_db._engine
    assert parent is not None

    closes: list[bool] = []
    real_dispose = parent.dispose
    monkeypatch.setattr(
        parent, "dispose", lambda close=True: (closes.append(close), real_dispose(close=close))
    )

    monkeypatch.setattr(os, "getpid", lambda: 999_999)
    sync_db.get_sync_session_factory()

    assert sync_db._engine is not parent
    assert closes == [False]
    assert sync_db._engine_pid == 999_999


def test_same_pid_keeps_engine(tmp_path) -> None:
    sync_db.set_database_url(f"sqlite:///{tmp_path / 'a.db'}")
    sync_db.get_sync_session_factory()
    first = sync_db._engine
    sync_db.get_sync_session_factory()
    assert sync_db._engine is first


def test_worker_process_init_drops_inherited_engine(tmp_path) -> None:
    from celery.signals import worker_process_init

    sync_db.set_database_url(f"sqlite:///{tmp_path / 'a.db'}")
    sync_db.get_sync_session_factory()
    assert sync_db._engine is not None

    worker_process_init.send(sender=None)

    assert sync_db._engine is None
    assert sync_db._session_factory is None


@pytest.mark.postgres
def test_forked_child_gets_its_own_postgres_connection() -> None:
    url = os.environ.get("SM_TEST_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("needs SM_TEST_DATABASE_URL on Postgres")
    sync_db.set_database_url(url)

    def backend_pid() -> int:
        with sync_db.sync_session() as s:
            return int(s.execute(text("select pg_backend_pid()")).scalar_one())

    parent_pid = backend_pid()
    r, w = os.pipe()
    child = os.fork()
    if child == 0:
        try:
            os.write(w, str(backend_pid()).encode())
        finally:
            os._exit(0)
    os.waitpid(child, 0)
    child_backend = int(os.read(r, 32))
    assert child_backend != parent_pid
    assert backend_pid() == parent_pid
