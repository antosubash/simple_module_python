"""Tests for the sync session factory's URL resolution.

The web process loads ``.env`` via pydantic-settings but never propagates the
result to ``os.environ``. ``set_database_url`` lets the module's
``on_startup`` pin the sync engine to whatever the host settings resolved,
so signals don't silently fall back to SQLite while the rest of the app
talks to Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from background_tasks import sync_db


@pytest.fixture(autouse=True)
def _reset_sync_db() -> Iterator[None]:
    sync_db.dispose_sync_engine()
    yield
    sync_db.dispose_sync_engine()


def test_resolve_url_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SM_DATABASE_URL", "sqlite:///./from-env.db")
    sync_db.set_database_url(None)

    assert sync_db._resolve_url() == "sqlite:///./from-env.db"


def test_set_database_url_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SM_DATABASE_URL", "sqlite:///./from-env.db")
    sync_db.set_database_url("postgresql+asyncpg://u:p@h/db")

    assert sync_db._resolve_url() == "postgresql+asyncpg://u:p@h/db"


def test_set_database_url_resets_engine_when_url_changes(tmp_path) -> None:
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    sync_db.set_database_url(f"sqlite:///{db_a}")
    factory_a = sync_db.get_sync_session_factory()
    sync_db.set_database_url(f"sqlite:///{db_a}")
    factory_a_again = sync_db.get_sync_session_factory()
    assert factory_a is factory_a_again, "same URL must reuse the cached factory"

    sync_db.set_database_url(f"sqlite:///{db_b}")
    factory_b = sync_db.get_sync_session_factory()
    assert factory_b is not factory_a, "URL change must dispose the old engine"


def test_dispose_sync_engine_clears_url_override(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'pinned.db'}"
    sync_db.set_database_url(url)
    assert sync_db._url_override == url

    sync_db.dispose_sync_engine()

    assert sync_db._url_override is None
