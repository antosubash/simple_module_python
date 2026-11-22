"""Lifespan teardown waits for contending lease-backend notifications (#1083)."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend_cleanup_helpers import Client
from fastapi import FastAPI
from simple_module_core.runtime import leases
from simple_module_hosting import _lifespan


async def test_teardown_closes_all_backends_during_contending_notifications(monkeypatch):
    initial, middle, final = Client(), Client(), Client()
    entered, release, removing, final_done, teardown_done = (Event() for _ in range(5))
    add_listener, remove_listener = leases._add_lease_listener, leases._remove_lease_listener
    listeners = {}

    def add(track):
        def notify(backend):
            if backend is middle:
                entered.set()
                assert release.wait(5)
            track(backend)

        listeners[track] = notify
        add_listener(notify)

    def remove(track):
        removing.set()
        assert final_done.wait(5)
        remove_listener(listeners.pop(track))

    def install_final():
        leases.configure_leases(final)
        final_done.set()

    def release_notification():
        try:
            assert removing.wait(5)
            if final_done.wait(0.1):
                # An unserialized final install lets teardown overtake middle.
                assert teardown_done.wait(5)
        finally:
            release.set()

    monkeypatch.setattr(_lifespan, "_add_lease_listener", add)
    monkeypatch.setattr(_lifespan, "_remove_lease_listener", remove)
    monkeypatch.setattr(_lifespan, "migration_status", AsyncMock(return_value={"is_current": True}))
    monkeypatch.setattr(_lifespan, "hydrate_settings_from_db", AsyncMock())
    app = FastAPI()
    app.state.sm = SimpleNamespace(db=SimpleNamespace(engine=object()))
    leases.configure_leases(initial)
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = []
        try:
            async with _lifespan.build_lifespan([], dispose_database=False)(app):
                pending.append(pool.submit(leases.configure_leases, middle))
                assert await asyncio.to_thread(entered.wait, 2)
                pending.append(pool.submit(install_final))
                pending.append(pool.submit(release_notification))
            teardown_done.set()
        finally:
            teardown_done.set()
            release.set()
            for future in pending:
                await asyncio.wait_for(asyncio.wrap_future(future), 5)
            for listener in listeners.values():
                remove_listener(listener)
    assert [backend.close_count for backend in (initial, middle, final)] == [1, 1, 1]
