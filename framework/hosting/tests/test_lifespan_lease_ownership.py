"""Overlapping apps share ownership of process-global lease backends (#1102)."""

import asyncio
from contextlib import AsyncExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from backend_cleanup_helpers import run_fork_probe
from fastapi import FastAPI
from simple_module_core.runtime.leases import InProcessLeaseBackend, configure_leases, lease
from simple_module_hosting import _lifespan
from simple_module_hosting.app_builder import create_app


class Backend(InProcessLeaseBackend):
    def __init__(self):
        super().__init__()
        self.close_count = 0

    async def acquire(self, name, token, ttl):
        assert self.close_count == 0, "lease backend was closed while still in use"
        return await super().acquire(name, token, ttl)

    async def aclose(self):
        self.close_count += 1


@pytest.mark.parametrize("first_to_exit", [0, 1])
@pytest.mark.parametrize("replace", [False, True])
async def test_overlapping_lifespans_close_shared_backends_only_after_last_exit(
    monkeypatch, first_to_exit, replace
):
    monkeypatch.setattr(_lifespan, "migration_status", AsyncMock(return_value={"is_current": True}))
    monkeypatch.setattr(_lifespan, "hydrate_settings_from_db", AsyncMock())
    initial, replacement = Backend(), Backend()
    configure_leases(initial)
    apps = [FastAPI(), FastAPI()]
    for app in apps:
        app.state.sm = SimpleNamespace(db=SimpleNamespace(engine=object()))

    async with AsyncExitStack() as cleanup:
        contexts = [AsyncExitStack() for _ in apps]
        for app, context in zip(apps, contexts, strict=True):
            await cleanup.enter_async_context(context)
            await context.enter_async_context(
                _lifespan.build_lifespan([], dispose_database=False)(app)
            )
        if replace:
            configure_leases(replacement)
        async with lease("before-exit", ttl=10, blocking=False) as held:
            await contexts[first_to_exit].aclose()
            assert await held.refresh()
            async with lease("after-exit", ttl=10, blocking=False):
                pass
        assert initial.close_count == replacement.close_count == 0

    assert initial.close_count == 1
    assert replacement.close_count == int(replace)


async def test_prebuilt_apps_keep_ownership_of_the_backends_they_installed(monkeypatch, settings):
    from simple_module_hosting import app_builder, leases

    monkeypatch.setattr(app_builder, "discover_modules", lambda **kwargs: [])
    monkeypatch.setattr(_lifespan, "migration_status", AsyncMock(return_value={"is_current": True}))
    monkeypatch.setattr(_lifespan, "hydrate_settings_from_db", AsyncMock())
    first, second = Backend(), Backend()
    backends = iter([first, second])
    monkeypatch.setattr(leases, "build_lease_backend", lambda *args, **kwargs: next(backends))
    settings.multi_tenant = False
    apps = [create_app(settings), create_app(settings)]

    async with apps[1].router.lifespan_context(apps[1]):
        async with apps[0].router.lifespan_context(apps[0]):
            pass
        assert first.close_count == 1
        assert second.close_count == 0
        async with lease("second-app", ttl=10, blocking=False):
            pass

    assert first.close_count == second.close_count == 1


async def test_lifespan_started_during_another_shutdown_keeps_the_backend(monkeypatch):
    monkeypatch.setattr(_lifespan, "migration_status", AsyncMock(return_value={"is_current": True}))
    monkeypatch.setattr(_lifespan, "hydrate_settings_from_db", AsyncMock())
    backend = Backend()
    configure_leases(backend)
    closing, resume = asyncio.Event(), asyncio.Event()

    class PausingStore:
        async def aclose(self):
            closing.set()
            await resume.wait()

    first, second = FastAPI(), FastAPI()
    first.state.sm = SimpleNamespace(
        db=SimpleNamespace(engine=object()), rate_limit_store=PausingStore()
    )
    second.state.sm = SimpleNamespace(db=SimpleNamespace(engine=object()))
    first_cm = _lifespan.build_lifespan([], dispose_database=False)(first)
    await first_cm.__aenter__()
    shutdown = asyncio.create_task(first_cm.__aexit__(None, None, None))
    try:
        await asyncio.wait_for(closing.wait(), timeout=5)
        async with _lifespan.build_lifespan([], dispose_database=False)(second):
            resume.set()
            await asyncio.wait_for(shutdown, timeout=5)
            assert backend.close_count == 0
            async with lease("second-app", ttl=10, blocking=False):
                pass
    finally:
        resume.set()
        if not shutdown.done():
            await asyncio.wait_for(shutdown, timeout=5)

    assert backend.close_count == 1


def test_fork_during_owner_registration_still_closes_all_backends():
    probe = """
import asyncio, os, signal, threading
from types import SimpleNamespace
from unittest.mock import AsyncMock
from fastapi import FastAPI
from simple_module_core.runtime.leases import configure_leases
from simple_module_hosting import _lifespan

closed = []
appended = threading.Event()

class Backend:
    def __init__(self, name):
        self.name = name

    async def aclose(self):
        closed.append(self.name)

class ObservedList(list):
    def append(self, backend):
        super().append(backend)
        appended.set()

_lifespan.migration_status = AsyncMock(return_value={"is_current": True})
_lifespan.hydrate_settings_from_db = AsyncMock()
configure_leases(Backend("initial"))
app = FastAPI()
app.state.sm = SimpleNamespace(db=SimpleNamespace(engine=object()))

async def main():
    cm = _lifespan.build_lifespan([], dispose_database=False)(app)
    await cm.__aenter__()
    tracker = next(ref() for ref in _lifespan._TRACKERS if ref() is not None)
    tracker.tracked = ObservedList(tracker.tracked)
    owners_lock = _lifespan._LEASE_OWNERS_LOCK
    owners_lock.acquire()
    thread = threading.Thread(target=configure_leases, args=(Backend("replacement"),))
    thread.start()
    try:
        assert appended.wait(2)
        pid = os.fork()
        if pid == 0:
            signal.alarm(3)
            code = 1
            try:
                await cm.__aexit__(None, None, None)
                assert closed == ["replacement", "initial"], closed
                code = 0
            except BaseException:
                import traceback
                traceback.print_exc()
            finally:
                os._exit(code)
    finally:
        owners_lock.release()
        thread.join(timeout=2)
        await cm.__aexit__(None, None, None)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 0

asyncio.run(main())
"""
    run_fork_probe(probe, timeout=10)
