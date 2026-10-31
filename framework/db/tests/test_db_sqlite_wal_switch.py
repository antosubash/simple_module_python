"""The per-connection WAL switch must tolerate a concurrent opener (fresh file)."""

from __future__ import annotations

import sqlite3

import pytest
from simple_module_db.session import _ensure_wal


class _Cursor:
    """A cursor whose switch loses the race; the winner leaves ``after``."""

    def __init__(self, before: str, after: str) -> None:
        self.mode = before
        self.after = after
        self.switches = 0

    def execute(self, sql: str):
        if sql == "PRAGMA journal_mode=WAL":
            self.switches += 1
            self.mode = self.after
            raise sqlite3.OperationalError("database is locked")
        return self

    def fetchone(self):
        return (self.mode,)


def test_already_wal_skips_the_switch():
    cursor = _Cursor("wal", "wal")
    _ensure_wal(cursor)
    assert cursor.switches == 0


def test_losing_the_switch_to_another_connection_is_fine():
    cursor = _Cursor("delete", "wal")
    _ensure_wal(cursor)
    assert cursor.switches == 1


def test_a_switch_still_in_progress_is_retried():
    cursor = _Cursor("delete", "delete")
    original = cursor.execute

    def execute(sql):
        if sql == "PRAGMA journal_mode=WAL" and cursor.switches == 2:
            cursor.mode = "wal"
            return cursor
        return original(sql)

    cursor.execute = execute
    _ensure_wal(cursor)
    assert (cursor.switches, cursor.mode) == (2, "wal")


def test_a_switch_that_leaves_the_file_unjournaled_still_raises():
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        _ensure_wal(_Cursor("delete", "delete"), timeout_ms=50)


def test_wal_file_opens_while_another_connection_writes(tmp_path):
    path = tmp_path / "app.db"
    writer = sqlite3.connect(path)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE t (x)")
    writer.commit()
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("INSERT INTO t VALUES (1)")
    reader = sqlite3.connect(path, timeout=0)
    try:
        _ensure_wal(reader.cursor())
        assert reader.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        reader.close()
        writer.rollback()
        writer.close()
