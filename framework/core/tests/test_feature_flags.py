"""Tests for FeatureFlagRegistry: defaults, overrides, listing."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI
from simple_module_core.feature_flags import (
    FeatureFlagDefinition,
    FeatureFlagRegistry,
    flag_enabled,
    is_flag_enabled,
    require_flag,
)


class TestFeatureFlagRegistry:
    async def test_add_and_check_default(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        assert reg.is_enabled("beta_ui") is False

    async def test_default_enabled(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="stable_feature", default_enabled=True))
        assert reg.is_enabled("stable_feature") is True

    async def test_override(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True)
        assert reg.is_enabled("beta_ui") is True

    async def test_clear_override(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True)
        reg.clear_override("beta_ui")
        assert reg.is_enabled("beta_ui") is False

    async def test_unknown_flag_is_disabled(self):
        reg = FeatureFlagRegistry()
        assert reg.is_enabled("nonexistent") is False

    async def test_all_flags(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="a"))
        reg.add(FeatureFlagDefinition(name="b"))
        assert len(reg.all_flags) == 2


class TestTenantOverrides:
    async def test_tenant_override_beats_system_override(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True)  # system on
        reg.set_override("beta_ui", False, tenant_id="acme")  # acme off

        assert reg.is_enabled("beta_ui", tenant_id="acme") is False
        assert reg.is_enabled("beta_ui", tenant_id="other") is True  # falls back to system
        assert reg.is_enabled("beta_ui") is True  # no tenant context: system value

    async def test_tenant_override_falls_back_to_default_when_no_system(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True, tenant_id="acme")

        assert reg.is_enabled("beta_ui", tenant_id="acme") is True
        assert reg.is_enabled("beta_ui", tenant_id="other") is False

    async def test_clear_tenant_override_only_clears_that_tenant(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True, tenant_id="acme")
        reg.set_override("beta_ui", True, tenant_id="globex")

        reg.clear_override("beta_ui", tenant_id="acme")

        assert reg.is_enabled("beta_ui", tenant_id="acme") is False
        assert reg.is_enabled("beta_ui", tenant_id="globex") is True

    async def test_clear_system_override_does_not_touch_tenant_overrides(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True)
        reg.set_override("beta_ui", True, tenant_id="acme")

        reg.clear_override("beta_ui")  # system

        assert reg.is_enabled("beta_ui") is False  # system gone, default false
        assert reg.is_enabled("beta_ui", tenant_id="acme") is True  # tenant intact

    async def test_inspectors_return_none_when_unset(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui"))
        assert reg.system_override("beta_ui") is None
        assert reg.tenant_override("beta_ui", "acme") is None


def _app_with_flag(registry: FeatureFlagRegistry, tenant_id: str | None = None) -> FastAPI:
    """Minimal FastAPI app wired with a registry on app.state.sm + optional tenant.

    Consumers in the real app read the registry off ``app.state.sm.feature_flags``
    and tenant off ``request.state.tenant_id``; this stubs just enough state for
    the helpers to exercise that exact lookup path.
    """
    app = FastAPI()
    app.state.sm = SimpleNamespace(feature_flags=registry)

    @app.middleware("http")
    async def _set_tenant(request, call_next):
        request.state.tenant_id = tenant_id
        return await call_next(request)

    @app.get("/check")
    async def check(
        on: Annotated[bool, Depends(flag_enabled("beta_ui"))],
    ) -> dict[str, bool]:
        return {"on": on}

    @app.get("/gated", dependencies=[Depends(require_flag("beta_ui"))])
    async def gated() -> dict[str, bool]:
        return {"reached": True}

    return app


class TestConsumerHelpers:
    async def test_flag_enabled_dep_yields_bool_for_request_tenant(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True, tenant_id="acme")

        app = _app_with_flag(reg, tenant_id="acme")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            assert (await c.get("/check")).json() == {"on": True}

    async def test_flag_enabled_dep_falls_back_to_system_without_tenant(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True)  # system on

        app = _app_with_flag(reg, tenant_id=None)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            assert (await c.get("/check")).json() == {"on": True}

    async def test_require_flag_404s_when_off(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))

        app = _app_with_flag(reg)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/gated")
            assert resp.status_code == 404

    async def test_require_flag_passes_when_on(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=True))

        app = _app_with_flag(reg)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/gated")
            assert resp.status_code == 200
            assert resp.json() == {"reached": True}

    async def test_require_flag_respects_tenant_override(self):
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=True))
        reg.set_override("beta_ui", False, tenant_id="acme")  # acme opts out

        app = _app_with_flag(reg, tenant_id="acme")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            assert (await c.get("/gated")).status_code == 404

    async def test_is_flag_enabled_reads_tenant_from_request_state(self):
        """Unit-level: the helper reads ``app.state.sm.feature_flags`` and
        ``request.state.tenant_id`` with no FastAPI dep machinery."""
        reg = FeatureFlagRegistry()
        reg.add(FeatureFlagDefinition(name="beta_ui", default_enabled=False))
        reg.set_override("beta_ui", True, tenant_id="acme")

        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(sm=SimpleNamespace(feature_flags=reg))),
            state=SimpleNamespace(tenant_id="acme"),
        )
        assert is_flag_enabled(request, "beta_ui") is True  # type: ignore[arg-type]

        request.state.tenant_id = "other"
        assert is_flag_enabled(request, "beta_ui") is False  # type: ignore[arg-type]
