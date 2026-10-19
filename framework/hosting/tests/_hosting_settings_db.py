"""Shared sqlite fixtures for the pre-app settings / secret-key tests.

A hand-built ``settings_setting`` table stands in for the migrated one, so the
pre-app read can be exercised without booting the app or running Alembic.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import NoReturn

_CREATE = (
    "CREATE TABLE settings_setting (id INTEGER PRIMARY KEY, scope TEXT NOT NULL, "
    "scope_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
    "value_type TEXT NOT NULL, UNIQUE (scope, scope_id, key))"
)


def seed_settings_db(
    db_path: Path, rows: list[tuple[str, ...]], value_type: str | None = None
) -> str:
    """Create the settings table, insert system-scope rows, return its URL.

    Rows are ``(key, value, value_type)``, or ``(key, value)`` when
    ``value_type`` is given for all of them.
    """
    if value_type is not None:
        rows = [(*row, value_type) for row in rows]
    conn = sqlite3.connect(db_path)
    conn.execute(_CREATE)
    conn.executemany(
        "INSERT INTO settings_setting (scope, scope_id, key, value, value_type) "
        "VALUES ('system', '', ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return f"sqlite+aiosqlite:///{db_path}"


def unmigrated_db_url(tmp_path: Path, name: str = "unmigrated.db") -> str:
    """A database file that exists but has no tables: never migrated."""
    db = tmp_path / name
    sqlite3.connect(db).close()
    return f"sqlite+aiosqlite:///{db}"


async def connection_refused(*_args: object) -> NoReturn:
    """Stands in for a database read that cannot reach the server."""
    raise OSError("Connection refused")
