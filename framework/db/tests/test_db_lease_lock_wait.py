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
