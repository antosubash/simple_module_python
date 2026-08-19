"""Module-declared CSP sources must reach the Content-Security-Policy header.

Wiring half of the ``register_csp_sources`` hook: ``run_module_registrations``
feeds the registry, and ``build_csp`` folds the collected origins into both
the dev CSP (Vite-widened) and the production default.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.csp import CspSourceRegistry
from simple_module_hosting._phase_helpers import build_csp
from simple_module_hosting._registrations import run_module_registrations
from simple_module_hosting.settings import Settings


class NeedsFont(ModuleBase):
    meta = ModuleMeta(name="NeedsFont")

    def register_csp_sources(self, registry: CspSourceRegistry) -> None:
        registry.add("style-src", "https://rsms.me")
        registry.add("font-src", "https://rsms.me")


def _filled_registry() -> CspSourceRegistry:
    reg = CspSourceRegistry()
    run_module_registrations(
        [NeedsFont()],
        app=MagicMock(),
        event_bus=MagicMock(),
        menu_registry=MagicMock(),
        perm_registry=MagicMock(),
        ff_registry=MagicMock(),
        health_registry=MagicMock(),
        public_route_registry=MagicMock(),
        design_pack_registry=MagicMock(),
        audit_link_registry=MagicMock(),
        csp_registry=reg,
    )
    return reg


class TestBuildCsp:
    def test_dev_csp_carries_module_sources_and_vite(self) -> None:
        dev = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="development")
        csp = build_csp(dev, _filled_registry())
        assert csp is not None
        assert "https://rsms.me" in csp
        assert dev.vite_dev_url in csp  # dev widening preserved

    def test_prod_csp_carries_module_sources(self) -> None:
        prod = Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            environment="production",
            secret_key="not-the-placeholder-secret-key-value",
        )
        csp = build_csp(prod, _filled_registry())
        assert csp is not None
        assert "https://rsms.me" in csp
        assert "localhost:5050" not in csp  # no dev widening in prod

    def test_empty_registry_keeps_existing_policies(self, settings: Settings) -> None:
        dev = build_csp(settings, CspSourceRegistry())
        assert dev is not None
        assert "https://fonts.googleapis.com" in dev
        assert "https://rsms.me" not in dev
