"""Settings and deferred hooks share one startup critical section (#1080)."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from simple_module_hosting.boot import _deferred_startup


@pytest.mark.parametrize("existing_lock", [False, True])
@pytest.mark.parametrize("pending", [False, True])
async def test_concurrent_replays_hydrate_and_persist_once(monkeypatch, pending, existing_lock):
    app = FastAPI()
    entered, resume = asyncio.Event(), asyncio.Event()
    events = []

    async def persist(app):
        events.append("persist")
        entered.set()
        await resume.wait()

    async def hydrate(app):
        events.append("hydrate")

    async def startup(app):
        events.append("startup")

    app.state.deferred_startup = [SimpleNamespace(on_startup=startup)] if pending else []
    if existing_lock:
        app.state.deferred_startup_lock = asyncio.Lock()
    monkeypatch.setattr(_deferred_startup, "persist_pending_secret_key", persist)
    monkeypatch.setattr(_deferred_startup, "hydrate_settings_from_db", hydrate)
    first = asyncio.create_task(_deferred_startup.run_deferred_startup(app))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        second = asyncio.create_task(_deferred_startup.run_deferred_startup(app))
        resume.set()
        await asyncio.wait_for(asyncio.gather(first, second), 2)
    finally:
        resume.set()
        await first
    assert events == (["persist", "hydrate", "startup"] if pending else ["persist", "hydrate"])
