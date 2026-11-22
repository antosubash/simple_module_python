"""Lifespan cleanup still runs when startup, serving, or shutdown fails."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from simple_module_core.leases import configure_leases
from simple_module_hosting import _lifespan


@pytest.fixture(autouse=True)
def reset_leases():
    yield
    configure_leases(None)


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
