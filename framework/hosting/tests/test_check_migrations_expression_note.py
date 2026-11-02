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
