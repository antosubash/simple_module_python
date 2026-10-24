"""The one clock every outbox timestamp is read from: the database's (GH #459).

Rows are written by web processes and claimed, leased and reclaimed by
workers on other hosts. Stamped with each process's own clock, a worker whose
clock lags the publisher's sees a fresh row as not yet due — the post-commit
dispatch then claims nothing and the event waits for the next sweep — and a
sweeper whose clock runs ahead shortens every other worker's lease. Reading
the time from the database gives every process the same clock.

On Postgres that is ``clock_timestamp()`` — the wall clock at the moment of the
call, not ``now()``, which is frozen at the start of the transaction. SQLite
has no server: every process sharing a SQLite file runs on the same host, so
the local clock already is the shared one.

Durations inside one delivery (how long the handler ran, for the backoff
after a failure) are measured with :func:`time.monotonic` and added to the
claim's database time, so a delivery needs no second round trip for its clock.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from simple_module_core.datetimes import aware as _aware
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _is_postgres(session: Any) -> bool:
    return session.get_bind().dialect.name == "postgresql"


async def db_now(session: Any) -> datetime:
    """The database's current time, as an aware UTC ``datetime``.

    *session* is an ``AsyncSession`` or a sync ``Session`` (a publisher may
    hold either).
    """
    if not _is_postgres(session):
        return datetime.now(UTC)
    stmt = select(func.clock_timestamp())
    if isinstance(session, Session):
        value = session.execute(stmt).scalar_one()
    else:
        value = (await session.execute(stmt)).scalar_one()
    return _aware(value).astimezone(UTC)


__all__ = ["db_now"]
