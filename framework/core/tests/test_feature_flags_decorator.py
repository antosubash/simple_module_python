"""Tests for the constant-based helpers and the ``@feature_flag`` decorator.

The older ``TestConsumerHelpers`` suite in ``test_feature_flags.py`` covers
the FastAPI dep factories with raw string flag names; the cases here
exercise the sibling behaviours: accepting a ``FeatureFlagDefinition``
directly, and the attribute-style decorator applied to endpoint
functions.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Annotated

import httpx
import pytest
from fastapi import Depends, FastAPI, Request
from simple_module_core.feature_flags import (
    FeatureFlagDefinition,
    FeatureFlagRegistry,
    feature_flag,
    flag_enabled,
    is_flag_enabled,
    require_flag,
)

FLAG_BETA_UI = FeatureFlagDefinition(name="beta_ui", default_enabled=False)


def _app_with_registry(registry: FeatureFlagRegistry, tenant_id: str | None = None) -> FastAPI:
    """FastAPI app with the registry wired on ``app.state.sm.feature_flags``."""
    app = FastAPI()
    app.state.sm = SimpleNamespace(feature_flags=registry)

    @app.middleware("http")
    async def _set_tenant(request, call_next):
        request.state.tenant_id = tenant_id
        return await call_next(request)

    return app


class TestDefinitionAcceptance:
    """Helpers accept ``FeatureFlagDefinition`` objects so callers pass the
    constant they registered instead of duplicating the string name."""

    async def test_is_flag_enabled_accepts_definition(self):
        reg = FeatureFlagRegistry()
        reg.add(FLAG_BETA_UI)
        reg.set_override(FLAG_BETA_UI.name, True)

        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(sm=SimpleNamespace(feature_flags=reg))),
            state=SimpleNamespace(tenant_id=None),
        )
        assert is_flag_enabled(request, FLAG_BETA_UI) is True  # type: ignore[arg-type]

    async def test_flag_enabled_and_require_flag_accept_definition(self):
        reg = FeatureFlagRegistry()
        reg.add(FLAG_BETA_UI)
        reg.set_override(FLAG_BETA_UI.name, True)

        app = _app_with_registry(reg)

        @app.get("/check")
        async def check(
            on: Annotated[bool, Depends(flag_enabled(FLAG_BETA_UI))],
        ) -> dict[str, bool]:
            return {"on": on}

        @app.get("/gated", dependencies=[Depends(require_flag(FLAG_BETA_UI))])
        async def gated() -> dict[str, bool]:
            return {"reached": True}

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            assert (await c.get("/check")).json() == {"on": True}
            assert (await c.get("/gated")).status_code == 200


class TestFeatureFlagDecorator:
    """``@feature_flag(FLAG)`` gates an endpoint function directly."""

    async def test_decorator_404s_when_off(self):
        reg = FeatureFlagRegistry()
        reg.add(FLAG_BETA_UI)
        app = _app_with_registry(reg)

        @app.get("/bulk")
        @feature_flag(FLAG_BETA_UI)
        async def bulk(request: Request) -> dict[str, bool]:
            return {"reached": True}

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            assert (await c.get("/bulk")).status_code == 404

    async def test_decorator_passes_when_on_and_accepts_raw_name(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=True))
        app = _app_with_registry(reg)

        @app.get("/bulk")
        @feature_flag("beta_ui")
        async def bulk(request: Request) -> dict[str, bool]:
            return {"reached": True}

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/bulk")
            assert resp.status_code == 200
            assert resp.json() == {"reached": True}

    async def test_decorator_respects_tenant_override(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=True))
        reg.set_override("beta_ui", False, tenant_id="acme")
        app = _app_with_registry(reg, tenant_id="acme")

        @app.get("/bulk")
        @feature_flag(FLAG_BETA_UI)
        async def bulk(request: Request) -> dict[str, bool]:
            return {"reached": True}

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            assert (await c.get("/bulk")).status_code == 404

    async def test_decorator_rejects_functions_without_request_param(self):
        """Defensive: the decorator needs a ``Request`` to read tenant state."""

        with pytest.raises(TypeError, match="must declare a 'request: Request' parameter"):

            @feature_flag(FLAG_BETA_UI)
            async def handler(payload: dict) -> dict:  # no request param
                return payload

    async def test_decorator_works_on_sync_handler(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=True))

        @feature_flag(FLAG_BETA_UI)
        def handler(request: Request) -> str:
            return "ok"

        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(sm=SimpleNamespace(feature_flags=reg))),
            state=SimpleNamespace(tenant_id=None),
        )
        assert handler(request) == "ok"  # type: ignore[arg-type]
