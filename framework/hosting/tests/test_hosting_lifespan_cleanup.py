"""Lifecycle failures must still unwind modules and dispose the engine (#634)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from simple_module_hosting import _lifespan


@pytest.mark.parametrize("failure", ["startup", "shutdown", "body", "migration"])
async def test_lifespan_unwinds_after_failure(monkeypatch, failure):
    calls = []
    app = FastAPI()

    async def dispose():
        calls.append("dispose")

    app.state.sm = SimpleNamespace(db=SimpleNamespace(engine=SimpleNamespace(dispose=dispose)))
    status = AsyncMock(return_value={"is_current": True})
    if failure == "migration":
        status.side_effect = RuntimeError("migration")
    monkeypatch.setattr(_lifespan, "migration_status", status)
    monkeypatch.setattr(_lifespan, "hydrate_settings_from_db", AsyncMock())
    modules = []
    for name in ["a", "b", "c"]:

        async def start(app, name=name):
            calls.append(f"start:{name}")
            if failure == "startup" and name == "b":
                raise RuntimeError("startup")

        async def stop(app, name=name):
            calls.append(f"stop:{name}")
            if failure in {"startup", "shutdown"} and name == "a":
                raise ValueError("cleanup")
            if failure == "shutdown" and name == "c":
                raise RuntimeError("shutdown")

        modules.append(SimpleNamespace(on_startup=start, on_shutdown=stop))

    with pytest.raises((RuntimeError, ValueError)):
        async with _lifespan.build_lifespan(modules)(app):
            if failure == "body":
                raise RuntimeError("body")

    expected = {
        "startup": ["start:a", "start:b", "stop:a", "dispose"],
        "shutdown": ["start:a", "start:b", "start:c", "stop:c", "stop:b", "stop:a", "dispose"],
        "body": ["start:a", "start:b", "start:c", "stop:c", "stop:b", "stop:a", "dispose"],
        "migration": ["dispose"],
    }
    assert calls == expected[failure]
