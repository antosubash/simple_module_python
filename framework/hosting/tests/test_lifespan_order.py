"""Verify ``create_app``'s lifespan walks modules forward and backward.

CLAUDE.md says ``on_startup`` runs in topological order and ``on_shutdown``
in reverse — a regression here means a dependent module's startup hook runs
before its dependency's hook is ready (or, on shutdown, the dependency tears
down resources while the dependent is still using them).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings

if TYPE_CHECKING:
    from fastapi import FastAPI


_calls: list[str] = []


class _TrackingModule(ModuleBase):
    """Records its own name into the module-level _calls list on each hook.

    Subclasses set their own ``meta`` so each one is identifiable inside
    the dependency graph; the hook bodies stay on the base.
    """

    async def on_startup(self, app: FastAPI) -> None:  # type: ignore[override]
        _calls.append(f"start:{self.meta.name}")

    async def on_shutdown(self, app: FastAPI) -> None:  # type: ignore[override]
        _calls.append(f"stop:{self.meta.name}")


class _ModA(_TrackingModule):
    meta = ModuleMeta(name="A")


class _ModB(_TrackingModule):
    meta = ModuleMeta(name="B", depends_on=["A"])


class _ModC(_TrackingModule):
    meta = ModuleMeta(name="C", depends_on=["B"])


@pytest.mark.anyio
async def test_lifespan_startup_forward_shutdown_reverse(monkeypatch) -> None:
    """Three modules A→B→C: startup must be A,B,C and shutdown C,B,A.

    We stub ``discover_modules`` rather than registering real entry points
    so this test stays hermetic; the topological-sort layer is exercised
    end-to-end by other tests already.
    """
    _calls.clear()
    instances: list[ModuleBase] = [_ModA(), _ModB(), _ModC()]

    async def _no_migration_check(engine, *args, **kwargs):
        return {"current_revision": None, "head_revision": None, "is_current": True}

    with (
        patch("simple_module_hosting.app_builder.discover_modules", return_value=instances),
        # Lives in _lifespan, not app_builder: the startup/shutdown sequence
        # was split out so app_builder stays focused on wiring.
        patch("simple_module_hosting._lifespan.check_migrations", _no_migration_check),
    ):
        settings = Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            environment="testing",
            secret_key="x" * 32,
            multi_tenant=False,
        )
        app = create_app(settings)

        ctx = app.router.lifespan_context(app)
        await ctx.__aenter__()
        await ctx.__aexit__(None, None, None)

    starts = [c for c in _calls if c.startswith("start:")]
    stops = [c for c in _calls if c.startswith("stop:")]
    assert starts == ["start:A", "start:B", "start:C"], _calls
    assert stops == ["stop:C", "stop:B", "stop:A"], _calls
