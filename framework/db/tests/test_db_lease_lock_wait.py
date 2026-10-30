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
