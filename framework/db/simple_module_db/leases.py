"""Database-backed :class:`~simple_module_core.leases.LeaseBackend` (GH #539).

The ``sm_lease`` table holds one row per ``(name, slot)``: a lease uses slot 0,
a semaphore slots ``0..n-1``, and slot ``-1`` keeps a semaphore's fence
counter. Rows are never deleted — a released or expired row is simply one whose
``expires_at`` has passed — so ``fence`` keeps increasing for the name's
lifetime.

Every comparison uses the *database* clock (read at the start of each
transaction), never this process's, so workers with skewed clocks agree on
who holds what. Atomicity comes from ``INSERT … ON CONFLICT DO NOTHING`` and
conditional ``UPDATE``\\ s, which serialise on the row on Postgres and on the
database lock on SQLite.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlmodel import Field

from simple_module_db.base import create_module_base
from simple_module_db.types import AwareDateTime

LEASE_METADATA_NAME: Final = "sm"
TABLE_LEASE: Final = "sm_lease"
NAME_MAX_LENGTH: Final = 255
HOLDER_MAX_LENGTH: Final = 255
_COUNTER_SLOT: Final = -1
_FREE: Final = ""
_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
_SQLITE_NOW: Final = text("strftime('%Y-%m-%d %H:%M:%f', 'now')")
# A write that matches nothing: on SQLite it takes the write lock (waiting out
# ``busy_timeout``) *before* the transaction reads, so two processes never both
# read and then race to upgrade a read lock into a write.
_SQLITE_WRITE_LOCK: Final = text("UPDATE sm_lease SET fence = fence WHERE 1 = 0")

Base = create_module_base(LEASE_METADATA_NAME)


class LeaseRow(Base, table=True):  # ty: ignore[unsupported-base]
    """One lease slot. ``holder`` is the owner's token, ``""`` when never held."""

    __tablename__ = TABLE_LEASE

    name: str = Field(primary_key=True, max_length=NAME_MAX_LENGTH)
    slot: int = Field(primary_key=True)
    holder: str = Field(default=_FREE, max_length=HOLDER_MAX_LENGTH)
    fence: int = Field(default=0)
    expires_at: datetime = Field(sa_type=AwareDateTime())


_T = LeaseRow.__table__


def _insert(dialect: str) -> Any:
    if dialect == "postgresql":
        return postgresql.insert(_T)
    if dialect == "sqlite":
        return sqlite.insert(_T)
    raise NotImplementedError(f"sm_lease supports postgresql and sqlite, not {dialect}")


async def _db_now(conn: AsyncConnection) -> datetime:
    if conn.dialect.name == "sqlite":
        raw = (await conn.execute(select(_SQLITE_NOW))).scalar_one()
        return datetime.fromisoformat(raw).replace(tzinfo=UTC)
    value = (await conn.execute(select(func.clock_timestamp()))).scalar_one()
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _row(name: str, slot: int) -> Any:
    return and_(_T.c.name == name, _T.c.slot == slot)


class DbLeaseBackend:
    """Leases in the ``sm_lease`` table, shared by every process on the database."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sqlite = engine.dialect.name == "sqlite"
        self._lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None

    def _guard(self) -> contextlib.AbstractAsyncContextManager[Any]:
        """Serialise this process's SQLite transactions (an in-memory database
        shares one connection); Postgres needs no process-side lock."""
        if not self._sqlite:
            return contextlib.nullcontext()
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock, self._lock_loop = asyncio.Lock(), loop
        return self._lock

    @contextlib.asynccontextmanager
    async def _tx(self) -> AsyncGenerator[tuple[AsyncConnection, datetime]]:
        async with self._guard(), self._engine.begin() as conn:
            if self._sqlite:
                await conn.execute(_SQLITE_WRITE_LOCK)
            yield conn, await _db_now(conn)

    async def _locked_now(self, conn: AsyncConnection, *where: Any) -> datetime:
        """Lock the matching rows on Postgres, then read the clock (#698).

        Postgres computes an UPDATE's new values before it waits on a row lock,
        so a time read first could grant (or "refresh") a lease that expired
        during the wait. SQLite holds the database write lock already.
        """
        await conn.execute(select(_T.c.slot).where(*where).with_for_update())
        return await _db_now(conn)

    async def _take_slot(
        self,
        conn: AsyncConnection,
        name: str,
        slot: int,
        token: str,
        ttl: float,
        now: datetime,
    ) -> int | None:
        """Claim *slot* if free (missing or expired) or already ours; return its fence."""
        if self._sqlite:
            values = {"holder": token, "expires_at": now + timedelta(seconds=ttl)}
            ins = _insert(conn.dialect.name).values(name=name, slot=slot, fence=1, **values)
            taken = (await conn.execute(ins.on_conflict_do_nothing())).rowcount == 1
        else:
            # An expired placeholder gives a missing slot a row to lock; the
            # UPDATE below then claims it exactly like an expired lease (fence 1).
            placeholder = _insert(conn.dialect.name).values(
                name=name, slot=slot, holder=_FREE, fence=0, expires_at=_EPOCH
            )
            await conn.execute(placeholder.on_conflict_do_nothing())
            now = await self._locked_now(conn, _row(name, slot))
            values = {"holder": token, "expires_at": now + timedelta(seconds=ttl)}
            taken = False
        if not taken:
            stmt = (
                update(_T)
                .where(_row(name, slot), (_T.c.expires_at <= now) | (_T.c.holder == token))
                .values(fence=_T.c.fence + 1, **values)
            )
            taken = (await conn.execute(stmt)).rowcount == 1
        if not taken:
            return None
        return (await conn.execute(select(_T.c.fence).where(_row(name, slot)))).scalar_one()

    async def _next_counter(self, conn: AsyncConnection, name: str) -> int:
        ins = _insert(conn.dialect.name).values(
            name=name, slot=_COUNTER_SLOT, holder=_FREE, fence=1, expires_at=_EPOCH
        )
        await conn.execute(
            ins.on_conflict_do_update(
                index_elements=[_T.c.name, _T.c.slot], set_={"fence": _T.c.fence + 1}
            )
        )
        stmt = select(_T.c.fence).where(_row(name, _COUNTER_SLOT))
        return (await conn.execute(stmt)).scalar_one()

    async def acquire(self, name: str, token: str, ttl: float) -> int | None:
        async with self._tx() as (conn, now):
            return await self._take_slot(conn, name, 0, token, ttl, now)

    async def semaphore_acquire(self, name: str, token: str, slots: int, ttl: float) -> int | None:
        async with self._tx() as (conn, now):
            mine = await self._slot_of(conn, name, token, now)
            order = [mine] if mine is not None else range(slots)
            for slot in order:
                if await self._take_slot(conn, name, slot, token, ttl, now) is not None:
                    return await self._next_counter(conn, name)
            return None

    async def _slot_of(
        self, conn: AsyncConnection, name: str, token: str, now: datetime
    ) -> int | None:
        stmt = select(_T.c.slot).where(
            _T.c.name == name, _T.c.slot >= 0, _T.c.holder == token, _T.c.expires_at > now
        )
        return (await conn.execute(stmt.limit(1))).scalar_one_or_none()

    async def _held_update(
        self, name: str, token: str, *, ttl: float | None, any_slot: bool
    ) -> bool:
        """Extend (``ttl``) or end (``None``) *token*'s unexpired hold."""
        async with self._tx() as (conn, now):
            where = [_T.c.name == name, _T.c.holder == token]
            where.append(_T.c.slot >= 0 if any_slot else _T.c.slot == 0)
            if not self._sqlite:
                now = await self._locked_now(conn, *where)
            where.append(_T.c.expires_at > now)
            expires = now if ttl is None else now + timedelta(seconds=ttl)
            result = await conn.execute(update(_T).where(*where).values(expires_at=expires))
            return result.rowcount > 0

    async def refresh(self, name: str, token: str, ttl: float) -> bool:
        return await self._held_update(name, token, ttl=ttl, any_slot=False)

    async def release(self, name: str, token: str) -> bool:
        return await self._held_update(name, token, ttl=None, any_slot=False)

    async def semaphore_refresh(self, name: str, token: str, ttl: float) -> bool:
        return await self._held_update(name, token, ttl=ttl, any_slot=True)

    async def semaphore_release(self, name: str, token: str) -> bool:
        return await self._held_update(name, token, ttl=None, any_slot=True)
