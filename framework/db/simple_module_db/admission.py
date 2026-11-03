"""SQLite writer serialization for transaction-owned admission checks."""

from sqlite3 import SQLITE_BUSY, SQLITE_LOCKED

from sqlalchemy import Table, false, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession


async def serialize_sqlite_writes(db: AsyncSession, table: Table, *, on_busy: Exception) -> None:
    """Acquire SQLite's writer lock before counting; hold it until transaction end.

    A zero-row UPDATE starts a real write transaction without modifying data.
    Use the connection so this no-op bypasses ORM ownership/audit rules and
    autoflush: pending admissions must not be flushed before taking the lock.
    Postgres callers retain their row/advisory locks.

    Under WAL an older read snapshot cannot upgrade after another writer
    commits (SQLITE_BUSY_SNAPSHOT). Let the caller supply its normal admission
    error or retryable conflict; never retry within the stale transaction.
    """
    if db.get_bind().dialect.name != "sqlite":
        return
    column = next(iter(table.primary_key.columns))
    try:
        connection = await db.connection()
        await connection.execute(update(table).where(false()).values({column: column}))
    except OperationalError as exc:
        code = getattr(exc.orig, "sqlite_errorcode", 0)
        if code & 0xFF in (SQLITE_BUSY, SQLITE_LOCKED):
            raise on_busy from exc
        raise
