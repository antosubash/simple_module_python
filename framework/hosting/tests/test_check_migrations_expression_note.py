"""check_migrations must not imply "clean" for what SQLite cannot verify (GH #342)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from simple_module_hosting.migrations import _note_unverifiable_expression_indexes


def _engine(dialect: str):
    return SimpleNamespace(dialect=SimpleNamespace(name=dialect))


def test_sqlite_logs_that_expression_indexes_are_unverified(caplog):
    pytest.importorskip("simple_module_users")
    with caplog.at_level(logging.INFO, logger="simple_module_hosting.migrations"):
        _note_unverifiable_expression_indexes(_engine("sqlite"))

    assert "cannot verify expression indexes" in caplog.text
    assert "ix_users_user_email_lower" in caplog.text
    assert "SM026" in caplog.text


def test_postgres_stays_quiet(caplog):
    with caplog.at_level(logging.INFO, logger="simple_module_hosting.migrations"):
        _note_unverifiable_expression_indexes(_engine("postgresql"))

    assert caplog.text == ""


def test_sqlite_that_has_the_index_stays_quiet(caplog, tmp_path):
    """GH #933: a migrated app's database already has it by name."""
    pytest.importorskip("simple_module_users")
    import sqlite3

    db = tmp_path / "app.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE users_user (id INTEGER PRIMARY KEY, email TEXT)")
        conn.execute("CREATE INDEX ix_users_user_email_lower ON users_user (lower(email))")
    engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"), url=f"sqlite:///{db}")
    with caplog.at_level(logging.INFO, logger="simple_module_hosting.migrations"):
        _note_unverifiable_expression_indexes(engine)

    assert "ix_users_user_email_lower" not in caplog.text
