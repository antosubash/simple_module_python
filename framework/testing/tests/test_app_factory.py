"""Tests for build_test_app + the bundled pytest fixtures."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, FastAPI
from simple_module_core import Event, ModuleBase, ModuleMeta


@dataclass
class _PingSent(Event):
    target: str = ""


class _EchoModule(ModuleBase):
    """A toy module used to exercise build_test_app — defines a single GET /ping route."""

    meta = ModuleMeta(
        name="Echo",
        route_prefix="/api/echo",
        view_prefix="/echo",
        requires_framework=">=1.0,<2.0",
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        @api_router.get("/ping")
        async def ping() -> dict:
            return {"pong": True}


class TestBuildTestApp:
    async def test_returns_fastapi_instance_from_class(self):
        """Passing a ModuleBase subclass instantiates it and returns a FastAPI app."""
        from simple_module_test import build_test_app

        app = build_test_app(_EchoModule)
        assert isinstance(app, FastAPI)

    async def test_returns_fastapi_instance_from_instance(self):
        """Accepts an already-instantiated module too."""
        from simple_module_test import build_test_app

        app = build_test_app(_EchoModule())
        assert isinstance(app, FastAPI)

    async def test_registers_module_routes_with_prefix(self):
        """The module's register_routes() runs and its api routes appear under the prefix."""
        from simple_module_test import build_test_app

        app = build_test_app(_EchoModule)
        paths = {getattr(r, "path", None) for r in app.routes}
        assert "/api/echo/ping" in paths

    async def test_module_accessible_on_app_state(self):
        """The instance is stored on app.state.module so tests can poke at it."""
        from simple_module_test import build_test_app

        app = build_test_app(_EchoModule)
        assert isinstance(app.state.module, _EchoModule)

    async def test_isolates_from_other_installed_modules(self):
        """build_test_app only mounts the given module — Products/Auth routes are absent."""
        from simple_module_test import build_test_app

        app = build_test_app(_EchoModule)
        paths = {getattr(r, "path", None) for r in app.routes}
        assert not any(p and p.startswith("/api/products") for p in paths)
        assert not any(p and p.startswith("/auth") for p in paths)


# ── pytest plugin fixtures ──────────────────────────────────────────


class TestPluginFixtures:
    async def test_fake_event_bus_fixture_is_fresh_each_test_part1(self, fake_event_bus):
        """First of a pair: publish an event and verify recording."""
        await fake_event_bus.publish(_PingSent(target="first"))
        assert len(fake_event_bus.events) == 1

    async def test_fake_event_bus_fixture_is_fresh_each_test_part2(self, fake_event_bus):
        """Second of the pair: if the fixture leaked state, we'd see the previous event."""
        assert fake_event_bus.events == []

    async def test_build_test_app_fixture_returns_callable(self, build_test_app):
        """The fixture exposes the helper as a callable, composable with other fixtures."""
        app = build_test_app(_EchoModule)
        assert isinstance(app, FastAPI)
