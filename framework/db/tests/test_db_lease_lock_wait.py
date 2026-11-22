"""A lease taken after waiting on a row lock is still valid when granted (#698)."""

import asyncio
import uuid

import pytest
from simple_module_db.leases import DbLeaseBackend, LeaseRow
from sqlalchemy import func, select

_T = LeaseRow.__table__


@pytest.mark.postgres
@pytest.mark.parametrize("operation", ["acquire", "refresh"])
async def test_postgres_lock_wait_does_not_consume_ttl(engine, operation):
    async with engine.begin() as conn:
        await conn.run_sync(LeaseRow.metadata.create_all)
    backend = DbLeaseBackend(engine)
    name = f"lockwait-{uuid.uuid4().hex}"
    holder = "old" if operation == "acquire" else "me"
    ttl = 0.01 if operation == "acquire" else 60
    assert await backend.acquire(name, holder, ttl) is not None
    await asyncio.sleep(0.05)  # intentional-sleep: let the 10 ms lease expire

    async with engine.connect() as blocker:
        await blocker.begin()
        row = (_T.c.name == name) & (_T.c.slot == 0)
        await blocker.execute(select(_T.c.fence).where(row).with_for_update())
        if operation == "acquire":
            pending = asyncio.create_task(backend.acquire(name, "new", 1.0))
        else:
            pending = asyncio.create_task(backend.refresh(name, "me", 1.0))
        await asyncio.sleep(1.5)  # intentional-sleep: hold the lock past the 1 s TTL
        await blocker.commit()
    assert await pending

    async with engine.connect() as conn:
        live = await conn.execute(select(_T.c.expires_at > func.clock_timestamp()).where(row))
        assert live.scalar_one() is True


@pytest.mark.parametrize(
    "operation",
    [
        "acquire",
        "refresh",
        "release",
        "semaphore_acquire",
        "semaphore_refresh",
        "semaphore_release",
    ],
)
@pytest.mark.parametrize("boundary", ["begin", "commit"])
@pytest.mark.parametrize("error_type", ["dbapi", "operational", "bug"])
async def test_database_outages_use_backend_unavailable_contract(
    monkeypatch, operation, boundary, error_type
):
    from contextlib import asynccontextmanager

    from sqlalchemy.exc import DBAPIError, OperationalError
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(LeaseRow.metadata.create_all)
    backend = DbLeaseBackend(engine)
    original_begin = engine.begin
    error = (
        RuntimeError("programming bug")
        if error_type == "bug"
        else (OperationalError if error_type == "operational" else DBAPIError)(
            "query", {}, OSError("connection lost")
        )
    )

    @asynccontextmanager
    async def broken_transaction(_engine):
        if boundary == "begin":
            raise error
        async with original_begin() as conn:
            yield conn
            raise error

    monkeypatch.setattr(type(engine), "begin", broken_transaction)
    args = ["outage", "holder"]
    if operation == "semaphore_acquire":
        args.append(2)
    if "release" not in operation:
        args.append(10)
    try:
        with pytest.raises(RuntimeError if error_type == "bug" else ConnectionError) as caught:
            await getattr(backend, operation)(*args)
        if error_type == "bug":
            assert caught.value is error
        else:
            assert caught.value.__cause__ is error
    finally:
        await engine.dispose()


@pytest.mark.parametrize("error_type", ["dns", "refused"])
async def test_raw_asyncpg_connect_outage_is_normalized(monkeypatch, error_type):
    import socket

    import asyncpg
    from simple_module_core.runtime.leases import Lease
    from sqlalchemy.ext.asyncio import create_async_engine

    error = socket.gaierror("DNS unavailable") if error_type == "dns" else ConnectionRefusedError()

    async def unavailable(*args, **kwargs):
        raise error

    monkeypatch.setattr(asyncpg, "connect", unavailable)
    engine = create_async_engine("postgresql+asyncpg://unused@localhost/unused")
    backend = DbLeaseBackend(engine)
    try:
        with pytest.raises(ConnectionError, match="Database lease backend unavailable") as caught:
            await backend.acquire("outage", "owner", 10)
        assert caught.value.__cause__ is error
        assert await Lease("outage", 10, backend=backend, blocking=False).acquire() is False
    finally:
        await engine.dispose()


@pytest.mark.parametrize("error_name", ["ProgrammingError", "IntegrityError", "DataError"])
async def test_database_bugs_propagate_unchanged(monkeypatch, error_name):
    import sqlalchemy.exc
    from simple_module_core.runtime.leases import Lease
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    error = getattr(sqlalchemy.exc, error_name)("query", {}, OSError("not an outage"))

    def fail(*args):
        raise error

    event.listen(engine.sync_engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(type(error)) as caught:
            await Lease("broken", 10, backend=DbLeaseBackend(engine), blocking=False).acquire()
        assert caught.value is error
    finally:
        await engine.dispose()


async def test_missing_lease_table_is_a_schema_error():
    import sqlite3

    from simple_module_core.runtime.leases import Lease
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        with pytest.raises(OperationalError, match="no such table: sm_lease") as caught:
            await Lease("missing", 10, backend=DbLeaseBackend(engine), blocking=False).acquire()
        assert caught.value.orig.sqlite_errorcode == sqlite3.SQLITE_ERROR
    finally:
        await engine.dispose()


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize(
    "sqlstate, unavailable",
    [
        ("08000", True),
        ("08006", True),
        ("08P01", True),
        ("57P01", True),
        ("57P02", True),
        ("57P03", True),
        ("53100", True),
        ("53200", True),
        ("53300", True),
        ("42601", False),
        ("23505", False),
        (None, False),
    ],
)
def test_postgres_unavailability_classification(sqlstate, unavailable, wrapped):
    from simple_module_db.leases import _is_unavailable_error
    from sqlalchemy.exc import DBAPIError

    error = Exception("driver failure")
    error.sqlstate = sqlstate
    if wrapped:
        error = DBAPIError("query", {}, error)
    assert _is_unavailable_error(error) is unavailable


@pytest.mark.parametrize("extended", [False, True])
@pytest.mark.parametrize(
    "code, unavailable",
    [
        (5, True),
        (6, True),
        (14, True),
        (10, True),
        (22, True),
        (15, True),
        (13, True),
        (7, True),
        (1, False),
        (19, False),
    ],
)
def test_sqlite_unavailability_classification(code, unavailable, extended):
    import sqlite3

    from simple_module_db.leases import _is_unavailable_error
    from sqlalchemy.exc import OperationalError

    error = sqlite3.OperationalError("driver failure")
    error.sqlite_errorcode = code | (256 if extended else 0)
    assert _is_unavailable_error(OperationalError("query", {}, error)) is unavailable


def test_unavailability_classification_for_timeouts_and_invalidated_connections():
    from simple_module_db.leases import _is_unavailable_error
    from sqlalchemy.exc import DataError, DBAPIError, IntegrityError, ProgrammingError
    from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

    for error in (TimeoutError(), OSError(), ConnectionError(), SqlAlchemyTimeoutError()):
        assert _is_unavailable_error(error)
    assert _is_unavailable_error(DBAPIError("query", {}, Exception(), connection_invalidated=True))
    assert not _is_unavailable_error(DBAPIError("query", {}, Exception()))
    assert not _is_unavailable_error(DBAPIError("query", {}, None))
    for error_type in (ProgrammingError, IntegrityError, DataError):
        error = error_type("query", {}, OSError(), connection_invalidated=True)
        assert not _is_unavailable_error(error)


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("error_name", ["DiskFullError", "OutOfMemoryError"])
async def test_postgres_resource_exhaustion_fails_nonblocking_acquire(
    monkeypatch, wrapped, error_name
):
    import asyncpg
    from simple_module_core.runtime.leases import Lease
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import create_async_engine

    driver_error = getattr(asyncpg, error_name)("resource exhausted")
    error = DBAPIError("query", {}, driver_error) if wrapped else driver_error

    async def unavailable(*args, **kwargs):
        raise error

    monkeypatch.setattr(asyncpg, "connect", unavailable)
    engine = create_async_engine("postgresql+asyncpg://unused@localhost/unused")
    backend = DbLeaseBackend(engine)
    try:
        with pytest.raises(ConnectionError) as caught:
            await backend.acquire("resource", "owner", 10)
        assert caught.value.__cause__ is error
        assert await Lease("resource", 10, backend=backend, blocking=False).acquire() is False
    finally:
        await engine.dispose()


async def test_real_sqlite_full_fails_nonblocking_acquire():
    import sqlite3

    from simple_module_core.runtime.leases import Lease
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    backend = DbLeaseBackend(engine)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(LeaseRow.metadata.create_all)
            await conn.execute(text("PRAGMA max_page_count = 1"))
        # Fill the existing pages using legal lease names; no new page can be allocated.
        for index in range(100):
            name = f"{index}:" + "x" * 240
            try:
                await backend.acquire(name, "owner", 10)
            except ConnectionError as error:
                assert error.__cause__.orig.sqlite_errorcode == sqlite3.SQLITE_FULL
                assert await Lease(name, 10, backend=backend, blocking=False).acquire() is False
                break
        else:
            pytest.fail("SQLite did not exhaust its page limit")
    finally:
        await engine.dispose()
