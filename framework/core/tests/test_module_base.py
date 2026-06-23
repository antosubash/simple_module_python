"""Tests for ModuleMeta and ModuleBase lifecycle/hooks."""

from __future__ import annotations

import pytest
from simple_module_core.events import EventBus
from simple_module_core.feature_flags import FeatureFlagRegistry
from simple_module_core.health import HealthRegistry
from simple_module_core.menu import MenuRegistry
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry


class TestModuleMeta:
    async def test_defaults(self):
        meta = ModuleMeta(name="TestModule")
        assert meta.name == "TestModule"
        assert meta.route_prefix == ""
        assert meta.view_prefix == ""
        assert meta.depends_on == []
        assert meta.version == "1.0.0"

    async def test_custom_fields(self):
        meta = ModuleMeta(
            name="Products",
            route_prefix="/api/products",
            view_prefix="/products",
            depends_on=["Auth"],
            version="2.0.0",
        )
        assert meta.route_prefix == "/api/products"
        assert meta.depends_on == ["Auth"]
        assert meta.version == "2.0.0"

    async def test_frozen(self):
        meta = ModuleMeta(name="Frozen")
        with pytest.raises(AttributeError):
            meta.name = "Changed"  # type: ignore[misc]


class DummyModule(ModuleBase):
    meta = ModuleMeta(name="Dummy", route_prefix="/api/dummy")

    def __init__(self):
        self.routes_registered = False

    def register_routes(self, api_router, view_router):
        self.routes_registered = True


class TestModuleBase:
    async def test_subclass_has_meta(self):
        mod = DummyModule()
        assert mod.meta.name == "Dummy"

    async def test_register_routes_override(self):
        mod = DummyModule()
        mod.register_routes(None, None)  # type: ignore[arg-type]
        assert mod.routes_registered is True

    async def test_default_noop_methods(self):
        """Default implementations should not raise."""
        mod = DummyModule()
        mod.register_menu_items(MenuRegistry())
        mod.register_permissions(PermissionRegistry())


class TestModuleLifecycle:
    async def test_on_startup_default_noop(self):
        mod = DummyModule()
        await mod.on_startup(None)

    async def test_on_shutdown_default_noop(self):
        mod = DummyModule()
        await mod.on_shutdown(None)

    async def test_register_event_handlers_default_noop(self):
        mod = DummyModule()
        bus = EventBus()
        mod.register_event_handlers(bus)

    async def test_register_feature_flags_default_noop(self):
        mod = DummyModule()
        reg = FeatureFlagRegistry()
        mod.register_feature_flags(reg)
        assert len(reg.all_flags) == 0


class TestModuleNewHooks:
    async def test_register_exception_handlers_default_noop(self):
        mod = DummyModule()
        mod.register_exception_handlers(None)

    async def test_register_health_checks_default_noop(self):
        mod = DummyModule()
        reg = HealthRegistry()
        mod.register_health_checks(reg)
        assert len(reg.all_checks) == 0

    async def test_register_settings_default_noop(self):
        mod = DummyModule()
        mod.register_settings(None)

    async def test_register_public_routes_default_noop(self):
        from simple_module_core.public_routes import PublicRouteRegistry

        mod = DummyModule()
        reg = PublicRouteRegistry()
        mod.register_public_routes(reg)
        assert reg.routes == []

    async def test_register_public_routes_override(self):
        from simple_module_core.public_routes import PublicRouteRegistry

        class ModWithPublic(ModuleBase):
            meta = ModuleMeta(name="WithPublic")

            def register_public_routes(self, registry):
                registry.add_prefix("/api/with-public/stac")
                registry.add_regex(r"/api/with-public/datasets/[^/]+/tilejson$", methods={"GET"})

        reg = PublicRouteRegistry()
        ModWithPublic().register_public_routes(reg)
        assert reg.matches("GET", "/api/with-public/stac/collections")
        assert reg.matches("GET", "/api/with-public/datasets/9/tilejson")
        assert not reg.matches("PATCH", "/api/with-public/datasets/9/tilejson")


class TestModuleAssetHooks:
    async def test_template_dirs_default_empty(self):
        """ModuleBase.template_dirs() returns an empty list by default."""
        mod = DummyModule()
        assert mod.template_dirs() == []

    async def test_static_mounts_default_empty(self):
        """ModuleBase.static_mounts() returns an empty dict by default."""
        mod = DummyModule()
        assert mod.static_mounts() == {}

    async def test_template_dirs_override(self, tmp_path):
        """A module can return its own template directory."""
        tpl_dir = tmp_path / "my_templates"
        tpl_dir.mkdir()

        class ModWithTpl(ModuleBase):
            meta = ModuleMeta(name="WithTpl")

            def template_dirs(self):
                return [tpl_dir]

        mod = ModWithTpl()
        result = mod.template_dirs()
        assert result == [tpl_dir]

    async def test_static_mounts_override(self, tmp_path):
        """A module can map URL prefixes to filesystem directories."""
        assets = tmp_path / "assets"
        assets.mkdir()

        class ModWithStatic(ModuleBase):
            meta = ModuleMeta(name="WithStatic")

            def static_mounts(self):
                return {"/modules/with-static": assets}

        mod = ModWithStatic()
        mounts = mod.static_mounts()
        assert mounts == {"/modules/with-static": assets}

    async def test_locale_dirs_default_empty(self):
        """ModuleBase.locale_dirs() returns an empty dict by default."""
        mod = DummyModule()
        assert mod.locale_dirs() == {}

    async def test_locale_dirs_override(self, tmp_path):
        """A module can map namespaces to locale directories."""
        locales = tmp_path / "locales"
        locales.mkdir()

        class ModWithLocales(ModuleBase):
            meta = ModuleMeta(name="WithLocales")

            def locale_dirs(self):
                return {"with_locales": locales}

        mod = ModWithLocales()
        dirs = mod.locale_dirs()
        assert dirs == {"with_locales": locales}
