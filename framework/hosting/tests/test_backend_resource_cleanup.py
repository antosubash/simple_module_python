"""Redis clients and lifespan-owned resources are released on teardown (#1083)."""

import asyncio
import gc
import weakref
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from simple_module_core.leases import configure_leases
from simple_module_hosting import _lifespan
from simple_module_hosting._lease_redis import RedisLeaseBackend
from simple_module_hosting._rate_limit_store import RedisWindowStore


class Client:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True
        self.closed_loop = asyncio.get_running_loop()

    async def eval(self, *args):
        assert not self.closed
        return 1


async def test_window_store_closes_client():
    client = Client()
    await RedisWindowStore(client).aclose()
    assert client.closed


def test_lease_backend_replaces_closed_loop_client_and_closes_each():
    clients = []

    def factory():
        client = Client()
        clients.append(client)
        return client

    backend = RedisLeaseBackend("redis://unused", factory=factory)

    async def first():
        assert await backend.acquire("key", "owner", 10) == 1
        assert await backend.acquire("other", "owner", 10) == 1
        return weakref.ref(asyncio.get_running_loop())

    async def second():
        assert await backend.acquire("key", "owner", 10) == 1
        await backend.aclose()
        await backend.aclose()

    previous_loop = asyncio.run(first())
    gc.collect()
    assert previous_loop() is None
    asyncio.run(second())
    assert len(clients) == 2
    assert all(client.closed for client in clients)


async def test_lease_backend_closes_superseded_client_on_running_owner_loop():
    import concurrent.futures

    clients = []
    ready = concurrent.futures.Future()

    def factory():
        client = Client()
        clients.append(client)
        return client

    backend = RedisLeaseBackend("redis://unused", factory=factory)
    owner = asyncio.new_event_loop()

    def serve():
        asyncio.set_event_loop(owner)
        owner.call_soon(ready.set_result, None)
        owner.run_forever()

    from threading import Thread

    thread = Thread(target=serve, daemon=True)
    thread.start()
    try:
        await asyncio.wait_for(asyncio.wrap_future(ready), 2)
        await asyncio.wait_for(
            asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(backend.acquire("key", "one", 10), owner)
            ),
            2,
        )
        assert await backend.acquire("key", "two", 10) == 1
        await backend.aclose()
        assert len(clients) == 2
        assert all(client.closed for client in clients)
        assert clients[0].closed_loop is owner
    finally:
        owner.call_soon_threadsafe(owner.stop)
        thread.join(timeout=2)
        owner.close()


@pytest.mark.parametrize("failure", [None, "startup", "migration", "body", "shutdown"])
@pytest.mark.parametrize("close_fails", [False, True])
async def test_lifespan_closes_backends_even_after_errors(
    monkeypatch, caplog, failure, close_fails
):
    events = []

    class Resource:
        async def aclose(self):
            events.append("close")
            if close_fails:
                raise RuntimeError("private connection details")

    async def dispose():
        events.append("dispose")

    async def status(engine):
        if failure == "migration":
            raise ValueError("migration")
        return {"is_current": True}

    async def hydrate(app):
        pass

    async def start(app):
        if failure == "startup":
            raise ValueError("startup")

    async def stop(app):
        events.append("stop")
        if failure == "shutdown":
            raise ValueError("shutdown")

    app = FastAPI()
    app.state.sm = SimpleNamespace(
        db=SimpleNamespace(engine=SimpleNamespace(dispose=dispose)), rate_limit_store=Resource()
    )
    configure_leases(Resource())
    monkeypatch.setattr(_lifespan, "migration_status", status)
    monkeypatch.setattr(_lifespan, "hydrate_settings_from_db", hydrate)

    async def boot():
        async with _lifespan.build_lifespan([SimpleNamespace(on_startup=start, on_shutdown=stop)])(
            app
        ):
            if failure == "body":
                raise ValueError("body")

    if failure:
        with pytest.raises(ValueError, match=failure):
            await boot()
    else:
        await boot()
    assert events == (
        ["close", "close", "dispose"]
        if failure in {"startup", "migration"}
        else ["stop", "close", "close", "dispose"]
    )
    if close_fails:
        assert "RuntimeError" in caplog.text
        assert "private connection details" not in caplog.text
