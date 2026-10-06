"""A first-run install boots behind head; failing on_startup hooks are deferred."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from simple_module_hosting._lifespan import build_lifespan, run_deferred_startup


def _module(name: str, *, fail_first: bool) -> SimpleNamespace:
    calls = {"n": 0}

    async def on_startup(app):
        calls["n"] += 1
        if fail_first and calls["n"] == 1:
            raise RuntimeError("no such table")

    return SimpleNamespace(
        meta=SimpleNamespace(name=name),
        on_startup=on_startup,
        on_shutdown=AsyncMock(),
        calls=calls,
    )


def _app() -> FastAPI:
    app = FastAPI()
    engine = SimpleNamespace(dispose=AsyncMock())
    app.state.sm = SimpleNamespace(db=SimpleNamespace(engine=engine))
    return app


async def _boot(app, modules, *, is_current: bool, first_run: bool):
    status = {"is_current": is_current, "pending_count": 0 if is_current else 1}
    with (
        patch("simple_module_hosting._lifespan.migration_status", AsyncMock(return_value=status)),
        patch("simple_module_hosting._lifespan._is_first_run", AsyncMock(return_value=first_run)),
        patch("simple_module_hosting._lifespan.hydrate_settings_from_db", AsyncMock()),
    ):
        async with build_lifespan(modules)(app):
            pass


async def test_failing_hook_is_deferred_then_replayed_on_unmigrated_first_run():
    app, good, bad = _app(), _module("good", fail_first=False), _module("bad", fail_first=True)
    seen = {}

    async def capture(app_):
        seen["deferred"] = [m.meta.name for m in app_.state.deferred_startup]

    with patch("simple_module_hosting._lifespan.hydrate_settings_from_db", AsyncMock()):
        status = {"is_current": False, "pending_count": 1}
        with (
            patch(
                "simple_module_hosting._lifespan.migration_status", AsyncMock(return_value=status)
            ),
            patch("simple_module_hosting._lifespan._is_first_run", AsyncMock(return_value=True)),
        ):
            async with build_lifespan([good, bad])(app):
                await capture(app)
                await run_deferred_startup(app)

    assert seen["deferred"] == ["bad"]
    assert good.calls["n"] == 1
    assert bad.calls["n"] == 2
    assert app.state.deferred_startup == []


async def test_failing_hook_still_aborts_boot_when_schema_is_current():
    app = _app()
    with pytest.raises(RuntimeError, match="no such table"):
        await _boot(app, [_module("bad", fail_first=True)], is_current=True, first_run=False)
