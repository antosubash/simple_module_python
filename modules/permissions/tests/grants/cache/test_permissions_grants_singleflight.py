"""Cold/expired grants coalesce; invalidated in-flight grants never authorize waiters."""

import asyncio
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from cachetools import TTLCache
from fastapi import FastAPI
from permissions.grants import source as grants
from simple_module_core.invalidation import Invalidation
from simple_module_core.singleflight import MAX_FILL_ATTEMPTS
from starlette.requests import Request


@pytest.mark.parametrize("invalidate", [None, "user", "all", "clear", "publish"])
@pytest.mark.parametrize("expired", [False, True])
async def test_grants_coalesce_and_discard_invalidated_reads(invalidate, expired):
    started, release = asyncio.Event(), asyncio.Event()
    reads = 0
    user = SimpleNamespace(id=uuid.uuid4())

    class DB:
        async def execute(self, stmt):
            nonlocal reads
            reads += 1
            keys = ["secret.view"] if reads == 1 else []
            started.set()
            await release.wait()
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: keys))

    @asynccontextmanager
    async def session():
        yield DB()

    app = FastAPI()
    app.state.sm = SimpleNamespace(db=SimpleNamespace(session_factory=session))
    request = Request({"type": "http", "app": app})
    now = [0]
    grants._CACHES[app] = TTLCache(maxsize=100, ttl=30, timer=lambda: now[0])
    if expired:
        grants._CACHES[app][user.id] = frozenset({"expired"})
        now[0] = 31
    tasks = [asyncio.create_task(grants.direct_grant_source(request, user)) for _ in range(50)]
    await started.wait()
    await asyncio.sleep(0)
    if invalidate == "clear":
        grants.clear_grants_cache()
    elif invalidate == "publish":
        await grants.publish_grants_changed(app, user.id)
    elif invalidate:
        grants.apply_invalidation(
            Invalidation(grants.CHANNEL, key=None if invalidate == "all" else str(user.id)), app
        )
    release.set()
    results = await asyncio.gather(*tasks)
    assert results == [frozenset() if invalidate else frozenset({"secret.view"})] * 50
    assert reads == (2 if invalidate else 1)
    assert not grants._FLIGHTS[app]._locks


async def test_grants_stop_retrying_under_continuous_invalidation():
    reads = 0
    user = SimpleNamespace(id=uuid.uuid4())

    class DB:
        async def execute(self, stmt):
            nonlocal reads
            reads += 1
            # Every read races an invalidation for some other user.
            grants.apply_invalidation(Invalidation(grants.CHANNEL, key=str(uuid.uuid4())))
            keys = [f"read-{reads}"]
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: keys))

    @asynccontextmanager
    async def session():
        yield DB()

    app = FastAPI()
    app.state.sm = SimpleNamespace(db=SimpleNamespace(session_factory=session))
    request = Request({"type": "http", "app": app})
    result = await grants.direct_grant_source(request, user)
    assert reads == MAX_FILL_ATTEMPTS
    assert result == frozenset({f"read-{MAX_FILL_ATTEMPTS}"})
    assert user.id not in grants._CACHES[app]
