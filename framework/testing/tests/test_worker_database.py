"""Each xdist worker gets its own Postgres database (``isolate_worker_database``)."""

from __future__ import annotations

import pytest
from simple_module_test import database

_PG = "postgresql+asyncpg://postgres:secret@db.local:5432/sm_test"


@pytest.fixture
def created(monkeypatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    async def fake_create(server_url, name):
        calls.append((server_url.database, name))

    monkeypatch.setattr(database, "_create_database_if_missing", fake_create)
    return calls


def test_a_worker_is_pointed_at_its_own_database(monkeypatch, created):
    monkeypatch.setenv(database.TEST_DATABASE_ENV, _PG)
    monkeypatch.setenv(database.XDIST_WORKER_ENV, "gw3")

    database.isolate_worker_database()

    assert created == [("sm_test", "sm_test_gw3")]
    assert database.database_url_for_tests() == (
        "postgresql+asyncpg://postgres:secret@db.local:5432/sm_test_gw3"
    )


def test_outside_xdist_the_named_database_is_used(monkeypatch, created):
    monkeypatch.setenv(database.TEST_DATABASE_ENV, _PG)
    monkeypatch.delenv(database.XDIST_WORKER_ENV, raising=False)

    database.isolate_worker_database()

    assert created == []
    assert database.database_url_for_tests() == _PG


def test_sqlite_workers_are_left_alone(monkeypatch, created):
    monkeypatch.delenv(database.TEST_DATABASE_ENV, raising=False)
    monkeypatch.setenv(database.XDIST_WORKER_ENV, "gw0")

    database.isolate_worker_database()

    assert created == []
    assert database.database_url_for_tests() == database.SQLITE_MEMORY
