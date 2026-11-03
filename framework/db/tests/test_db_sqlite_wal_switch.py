"""The per-connection WAL switch must tolerate a concurrent opener (fresh file)."""

from __future__ import annotations

import sqlite3
import threading

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


def test_fresh_file_waits_for_a_concurrent_switch(tmp_path):
    """The old one-shot switch failed here at once: the other opener held a lock."""
    path = tmp_path / "app.db"
    other = sqlite3.connect(path, check_same_thread=False)
    other.execute("CREATE TABLE t (x)")
    other.commit()
    other.execute("BEGIN IMMEDIATE")
    other.execute("INSERT INTO t VALUES (1)")

    def finish_and_switch():
        other.commit()
        other.execute("PRAGMA journal_mode=WAL")

    timer = threading.Timer(0.2, finish_and_switch)
    opener = sqlite3.connect(path, timeout=0)
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            opener.execute("PRAGMA journal_mode=WAL")
        timer.start()
        _ensure_wal(opener.cursor(), timeout_ms=5000)
        assert opener.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        timer.join()
        opener.close()
        other.close()
