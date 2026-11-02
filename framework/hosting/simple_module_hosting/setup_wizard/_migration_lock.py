"""Database advisory locks that also work before the first migration (#634)."""

import logging
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

_POSTGRES_LOCK = 634539


@contextmanager
def migration_lock(url: URL) -> Generator[None]:
    """Hold until the migration thread exits; no TTL or request cancellation gap."""
    if url.get_backend_name() == "sqlite":
        if not url.database or url.database == ":memory:":
            # An in-memory database cannot be shared by different workers.
            yield
            return
        import sqlite3

        # A separate SQLite database supplies the advisory lock without locking
        # the application database against Alembic's own connections.
        path = str(Path(url.database).resolve()) + ".migrate-lock.db"
        with closing(sqlite3.connect(path, timeout=300)) as connection:
            try:
                connection.execute("BEGIN EXCLUSIVE")
                yield
            finally:
                connection.rollback()
        return
    if url.get_backend_name() != "postgresql":
        logger.warning(
            "No cross-worker migration lock for %s; relying on the per-process lock",
            url.get_backend_name(),
        )
        yield
        return
    engine = create_engine(url.set(drivername="postgresql+psycopg2"), poolclass=NullPool)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT pg_advisory_lock(%s)", (_POSTGRES_LOCK,))
            try:
                yield
            finally:
                connection.exec_driver_sql("SELECT pg_advisory_unlock(%s)", (_POSTGRES_LOCK,))
    finally:
        engine.dispose()
