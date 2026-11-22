"""Lifespan cleanup still runs when startup, serving, or shutdown fails."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from simple_module_core.leases import configure_leases
from simple_module_hosting import _lifespan


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


@pytest.mark.parametrize("startup_fails", [False, True])
async def test_lifespan_closes_every_replacement_once_in_reverse_order(monkeypatch, startup_fails):
    from contextlib import nullcontext
    from unittest.mock import AsyncMock

    events = []

    class Backend:
        def __init__(self, name):
            self.name = name

        async def aclose(self):
            events.append(self.name)

    initial, middle, final = [Backend(name) for name in ("initial", "middle", "final")]
    configure_leases(initial)
    app = FastAPI()
    app.state.sm = SimpleNamespace(
        db=SimpleNamespace(engine=object()), rate_limit_store=Backend("rate")
    )

    async def start(app):
        configure_leases(middle)
        configure_leases(final)
        configure_leases(middle)  # Reinstalling a backend must not close it twice.
        configure_leases(final)
        if startup_fails:
            raise ValueError("startup")

    monkeypatch.setattr(_lifespan, "migration_status", AsyncMock(return_value={"is_current": True}))
    monkeypatch.setattr(_lifespan, "hydrate_settings_from_db", AsyncMock())
    module = SimpleNamespace(on_startup=start, on_shutdown=AsyncMock())
    expected = pytest.raises(ValueError, match="startup") if startup_fails else nullcontext()
    with expected:
        async with _lifespan.build_lifespan([module], dispose_database=False)(app):
            assert events == []
    assert events == ["rate", "final", "middle", "initial"]
    configure_leases(Backend("after_lifespan"))
    assert events == ["rate", "final", "middle", "initial"]


async def test_lifespan_cancellation_still_closes_remaining_backends_and_engine(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock

    events = []

    class CancellingRateStore:
        async def aclose(self):
            events.append("rate_cancel")
            raise asyncio.CancelledError

    class Backend:
        def __init__(self, name):
            self.name = name

        async def aclose(self):
            events.append(self.name)

    async def dispose():
        events.append("dispose")

    configure_leases(Backend("initial"))
    app = FastAPI()
    app.state.sm = SimpleNamespace(
        db=SimpleNamespace(engine=SimpleNamespace(dispose=dispose)),
        rate_limit_store=CancellingRateStore(),
    )

    async def start(app):
        configure_leases(Backend("final"))

    monkeypatch.setattr(_lifespan, "migration_status", AsyncMock(return_value={"is_current": True}))
    monkeypatch.setattr(_lifespan, "hydrate_settings_from_db", AsyncMock())
    module = SimpleNamespace(on_startup=start, on_shutdown=AsyncMock())
    with pytest.raises(asyncio.CancelledError):
        async with _lifespan.build_lifespan([module])(app):
            pass
    assert events == ["rate_cancel", "final", "initial", "dispose"]
