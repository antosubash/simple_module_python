"""Concurrent misses must share successful reads without sharing stale authorization."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from cachetools import TTLCache
from fastapi import FastAPI
from tenants import resolver
from tenants.service import TenantService


@pytest.mark.parametrize("invalidate", [None, "same", "all"])
@pytest.mark.parametrize("expired", [False, True])
async def test_memberships_coalesce_and_retry_invalidation(monkeypatch, invalidate, expired):
    app = FastAPI()
    now = [0]
    monkeypatch.setattr(
        resolver, "_MEMBERSHIPS", TTLCache(maxsize=100, ttl=60, timer=lambda: now[0])
    )
    if expired:
        resolver._MEMBERSHIPS["same"] = []
        now[0] = 61

    @asynccontextmanager
    async def session():
        yield None

    app.state.sm = SimpleNamespace(db=SimpleNamespace(session_factory=session))
    started, release = asyncio.Event(), asyncio.Event()
    reads = 0

    async def read(self, user_id):
        nonlocal reads
        reads += 1
        started.set()
        rows = (
            [
                (
                    SimpleNamespace(
                        id="org", slug="org", name="Org", status="active", created_at=None
                    ),
                    "owner",
                )
            ]
            if reads == 1
            else []
        )
        await release.wait()
        return rows

    monkeypatch.setattr(TenantService, "list_for_user", read)
    tasks = [asyncio.create_task(resolver.memberships_for(app, "same")) for _ in range(50)]
    await started.wait()
    await asyncio.sleep(0)
    if invalidate:
        resolver.forget(None if invalidate == "all" else "same")
    release.set()
    results = await asyncio.gather(*tasks)
    assert [[m.role for m in result] for result in results] == (
        [[]] if invalidate else [["owner"]]
    ) * 50
    assert not resolver._FLIGHTS[app]._locks
    assert reads == (2 if invalidate else 1)
