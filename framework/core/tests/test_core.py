"""Tests for the framework core: module system, menu, permissions, feature flags, events."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from simple_module_core.diagnostics import (
    Diagnostic,
    DiagnosticLevel,
    MigrationDiagnostics,
    print_diagnostics,
)
from simple_module_core.discovery import discover_modules, topological_sort
from simple_module_core.events import Event, EventBus
from simple_module_core.exceptions import CircularDependencyError, InvalidModuleError
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from simple_module_core.health import HealthCheck, HealthCheckResult, HealthRegistry, HealthStatus
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

# ── ModuleMeta ───────────────────────────────────────────────────────


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
            meta.name = "Changed"  # type: ignore[misc]  # ty: ignore[invalid-assignment]


# ── ModuleBase ───────────────────────────────────────────────────────


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


# ── MenuRegistry ─────────────────────────────────────────────────────


class TestMenuRegistry:
    async def test_add_and_all_items(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Dashboard", url="/dashboard", order=1))
        reg.add(MenuItem(label="Products", url="/products", order=2))
        assert len(reg.all_items) == 2
        assert reg.all_items[0].label == "Dashboard"

    async def test_add_many(self):
        reg = MenuRegistry()
        reg.add_many(
            [
                MenuItem(label="A", url="/a", order=1),
                MenuItem(label="B", url="/b", order=2),
            ]
        )
        assert len(reg.all_items) == 2

    async def test_sorted_by_order(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Z", url="/z", order=99))
        reg.add(MenuItem(label="A", url="/a", order=1))
        assert reg.all_items[0].label == "A"
        assert reg.all_items[1].label == "Z"

    async def test_filter_unauthenticated(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Public", url="/pub", requires_auth=False))
        reg.add(MenuItem(label="Private", url="/priv", requires_auth=True))

        result = reg.get_for_user(is_authenticated=False)
        sidebar = result["sidebar"]
        assert len(sidebar) == 1
        assert sidebar[0]["label"] == "Public"

    async def test_filter_authenticated_sees_all(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Public", url="/pub", requires_auth=False))
        reg.add(MenuItem(label="Private", url="/priv", requires_auth=True))

        result = reg.get_for_user(is_authenticated=True)
        sidebar = result["sidebar"]
        assert len(sidebar) == 2

    async def test_filter_by_roles(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Admin Panel", url="/admin", roles=["admin"]))
        reg.add(MenuItem(label="Dashboard", url="/dash"))

        # User without admin role
        result = reg.get_for_user(is_authenticated=True, roles=["user"])
        sidebar = result["sidebar"]
        labels = [i["label"] for i in sidebar]
        assert "Dashboard" in labels
        assert "Admin Panel" not in labels

        # User with admin role
        result = reg.get_for_user(is_authenticated=True, roles=["admin"])
        sidebar = result["sidebar"]
        labels = [i["label"] for i in sidebar]
        assert "Admin Panel" in labels

    async def test_sections(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Side", url="/s", section=MenuSection.SIDEBAR))
        reg.add(MenuItem(label="Nav", url="/n", section=MenuSection.NAVBAR))
        reg.add(MenuItem(label="Drop", url="/d", section=MenuSection.USER_DROPDOWN))

        result = reg.get_for_user(is_authenticated=True)
        assert len(result["sidebar"]) == 1
        assert len(result["navbar"]) == 1
        assert len(result["userDropdown"]) == 1


# ── PermissionRegistry ───────────────────────────────────────────────


class TestPermissionRegistry:
    async def test_add_group(self):
        reg = PermissionRegistry()
        reg.add_group("Products", ["products.view", "products.create"])
        assert "products.view" in reg.all_permissions
        assert "products.create" in reg.all_permissions

    async def test_add_single(self):
        reg = PermissionRegistry()
        reg.add("orders.view")
        assert reg.has("orders.view")

    async def test_auto_grouping(self):
        reg = PermissionRegistry()
        reg.add("orders.view")
        reg.add("orders.create")
        groups = reg.groups
        assert any(g.name == "orders" for g in groups)

    async def test_has(self):
        reg = PermissionRegistry()
        reg.add("test.perm")
        assert reg.has("test.perm") is True
        assert reg.has("nonexistent") is False

    async def test_admin_role_gets_all(self):
        reg = PermissionRegistry()
        reg.add_group("Products", ["products.view", "products.edit"])
        perms = reg.get_permissions_for_roles(["admin"])
        assert "products.view" in perms
        assert "products.edit" in perms

    async def test_non_admin_gets_none_by_default(self):
        reg = PermissionRegistry()
        reg.add_group("Products", ["products.view"])
        perms = reg.get_permissions_for_roles(["user"])
        assert len(perms) == 0

    async def test_custom_role_map(self):
        reg = PermissionRegistry()
        reg.add_group("Products", ["products.view", "products.edit"])
        role_map = {"editor": ["products.edit"]}
        perms = reg.get_permissions_for_roles(["editor"], role_permission_map=role_map)
        assert "products.edit" in perms
        assert "products.view" not in perms

    async def test_extend_existing_group(self):
        reg = PermissionRegistry()
        reg.add_group("Products", ["products.view"])
        reg.add_group("Products", ["products.delete"])
        perms = reg.all_permissions
        assert "products.view" in perms
        assert "products.delete" in perms


# ── FeatureFlagRegistry ──────────────────────────────────────────────


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


# ── EventBus ─────────────────────────────────────────────────────────


@dataclass
class OrderCreated(Event):
    order_id: int = 0


class TestEventBus:
    async def test_subscribe_and_publish(self):
        bus = EventBus()
        received: list[Event] = []

        async def handler(event: OrderCreated):
            received.append(event)

        bus.subscribe(OrderCreated, handler)
        await bus.publish(OrderCreated(order_id=42))

        assert len(received) == 1
        assert received[0].order_id == 42  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    async def test_multiple_handlers(self):
        bus = EventBus()
        calls: list[str] = []

        async def handler_a(event: OrderCreated):
            calls.append("a")

        async def handler_b(event: OrderCreated):
            calls.append("b")

        bus.subscribe(OrderCreated, handler_a)
        bus.subscribe(OrderCreated, handler_b)
        await bus.publish(OrderCreated())

        assert "a" in calls
        assert "b" in calls

    async def test_no_handlers_no_error(self):
        bus = EventBus()
        await bus.publish(OrderCreated())  # Should not raise

    async def test_handler_error_does_not_propagate(self):
        bus = EventBus()
        calls: list[str] = []

        async def bad_handler(event: OrderCreated):
            raise ValueError("boom")

        async def good_handler(event: OrderCreated):
            calls.append("ok")

        bus.subscribe(OrderCreated, bad_handler)
        bus.subscribe(OrderCreated, good_handler)
        await bus.publish(OrderCreated())

        # The good handler should still have been called
        assert "ok" in calls


# ── Discovery / topological_sort ─────────────────────────────────────


class ModA(ModuleBase):
    meta = ModuleMeta(name="A")


class ModB(ModuleBase):
    meta = ModuleMeta(name="B", depends_on=["A"])


class ModC(ModuleBase):
    meta = ModuleMeta(name="C", depends_on=["B"])


class CycleX(ModuleBase):
    meta = ModuleMeta(name="X", depends_on=["Y"])


class CycleY(ModuleBase):
    meta = ModuleMeta(name="Y", depends_on=["X"])


class TestTopologicalSort:
    async def test_valid_dag(self):
        modules = [ModC(), ModA(), ModB()]
        sorted_mods = topological_sort(modules)
        names = [m.meta.name for m in sorted_mods]
        assert names.index("A") < names.index("B")
        assert names.index("B") < names.index("C")

    async def test_no_dependencies(self):
        modules = [ModA()]
        sorted_mods = topological_sort(modules)
        assert len(sorted_mods) == 1
        assert sorted_mods[0].meta.name == "A"

    async def test_circular_dependency_raises(self):
        modules = [CycleX(), CycleY()]
        with pytest.raises(CircularDependencyError):
            topological_sort(modules)


class TestDiscoverModules:
    async def test_discover_finds_installed_modules(self):
        """discover_modules() should find modules registered via entry_points."""
        from simple_module_core.discovery import discover_modules

        modules = discover_modules()
        names = [m.meta.name for m in modules]
        # The workspace has Auth, Products, Dashboard registered
        assert "Products" in names
        assert "Auth" in names
        assert "Dashboard" in names


# ── Topological Sort Edge Cases ─────────────────────────────────────


class TestTopologicalSortEdgeCases:
    async def test_diamond_dependency(self):
        """A -> B, A -> C, B -> D, C -> D (diamond, not cycle)."""

        class ModD(ModuleBase):
            meta = ModuleMeta(name="D")

        class ModB2(ModuleBase):
            meta = ModuleMeta(name="B2", depends_on=["D"])

        class ModC2(ModuleBase):
            meta = ModuleMeta(name="C2", depends_on=["D"])

        class ModA2(ModuleBase):
            meta = ModuleMeta(name="A2", depends_on=["B2", "C2"])

        modules = [ModA2(), ModC2(), ModB2(), ModD()]
        sorted_mods = topological_sort(modules)
        names = [m.meta.name for m in sorted_mods]
        assert names.index("D") < names.index("B2")
        assert names.index("D") < names.index("C2")
        assert names.index("B2") < names.index("A2")

    async def test_missing_dependency_ignored(self):
        """A module depending on a non-installed module should not crash."""

        class ModWithMissing(ModuleBase):
            meta = ModuleMeta(name="Lonely", depends_on=["NonExistent"])

        sorted_mods = topological_sort([ModWithMissing()])
        assert len(sorted_mods) == 1

    async def test_self_dependency_raises(self):
        """A module that depends on itself is a cycle."""

        class SelfDep(ModuleBase):
            meta = ModuleMeta(name="Self", depends_on=["Self"])

        with pytest.raises(CircularDependencyError):
            topological_sort([SelfDep()])

    async def test_three_node_cycle(self):
        """A -> B -> C -> A should raise."""

        class CA(ModuleBase):
            meta = ModuleMeta(name="CA", depends_on=["CC"])

        class CB(ModuleBase):
            meta = ModuleMeta(name="CB", depends_on=["CA"])

        class CC(ModuleBase):
            meta = ModuleMeta(name="CC", depends_on=["CB"])

        with pytest.raises(CircularDependencyError):
            topological_sort([CA(), CB(), CC()])

    async def test_empty_list(self):
        assert topological_sort([]) == []


# ── EventBus Advanced ───────────────────────────────────────────────


class TestEventBusAdvanced:
    async def test_different_event_types_isolated(self):
        """Handlers only receive events of their subscribed type."""
        bus = EventBus()

        @dataclass
        class EventA(Event):
            pass

        @dataclass
        class EventB(Event):
            pass

        a_calls: list = []
        b_calls: list = []

        async def handle_a(e):
            a_calls.append(e)

        async def handle_b(e):
            b_calls.append(e)

        bus.subscribe(EventA, handle_a)
        bus.subscribe(EventB, handle_b)

        await bus.publish(EventA())
        assert len(a_calls) == 1
        assert len(b_calls) == 0

        await bus.publish(EventB())
        assert len(b_calls) == 1

    async def test_publish_nowait(self):
        """publish_nowait should schedule without blocking."""
        import asyncio

        bus = EventBus()
        received: list = []

        async def handler(e):
            received.append(e)

        bus.subscribe(OrderCreated, handler)
        bus.publish_nowait(OrderCreated(order_id=99))
        await asyncio.sleep(0.05)
        assert len(received) == 1
        assert received[0].order_id == 99

    async def test_subclass_events_do_not_match_parent_subscription(self):
        """Subscribing to a base Event class should not receive subclass events."""
        bus = EventBus()

        @dataclass
        class Parent(Event):
            pass

        @dataclass
        class Child(Parent):
            pass

        calls: list = []

        async def parent_handler(e):
            calls.append(("parent", e))

        bus.subscribe(Parent, parent_handler)
        await bus.publish(Child())

        # Child events should not trigger Parent handlers — strict type match.
        assert calls == []

    async def test_publish_with_no_subscribers_returns_none(self):
        """publish() should resolve to None when nothing is listening."""
        bus = EventBus()

        @dataclass
        class Orphan(Event):
            pass

        result = await bus.publish(Orphan())
        assert result is None

    async def test_publish_nowait_with_no_subscribers_is_noop(self):
        """publish_nowait() on an unheard event should not raise."""
        bus = EventBus()

        @dataclass
        class Orphan(Event):
            pass

        bus.publish_nowait(Orphan())  # must not raise

    async def test_handlers_dispatched_concurrently(self):
        """All handlers for an event should run concurrently via gather."""
        import asyncio

        bus = EventBus()
        order: list[str] = []

        async def slow(e):
            await asyncio.sleep(0.02)
            order.append("slow")

        async def fast(e):
            order.append("fast")

        bus.subscribe(OrderCreated, slow)
        bus.subscribe(OrderCreated, fast)
        await bus.publish(OrderCreated(order_id=1))

        # "fast" should complete before "slow" because they run concurrently.
        assert order == ["fast", "slow"]


# ── MenuRegistry Advanced ───────────────────────────────────────────


class TestMenuRegistryAdvanced:
    async def test_multiple_roles_any_match(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Editor", url="/edit", roles=["editor", "admin"]))
        result = reg.get_for_user(is_authenticated=True, roles=["editor"])
        assert len(result["sidebar"]) == 1

    async def test_empty_registry(self):
        reg = MenuRegistry()
        result = reg.get_for_user(is_authenticated=True)
        assert all(len(v) == 0 for v in result.values())

    async def test_admin_sidebar_section(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Users", url="/admin/users", section=MenuSection.ADMIN_SIDEBAR))
        result = reg.get_for_user(is_authenticated=True)
        assert len(result["adminSidebar"]) == 1

    async def test_icon_preserved(self):
        reg = MenuRegistry()
        reg.add(MenuItem(label="Home", url="/", icon="home"))
        result = reg.get_for_user(is_authenticated=True)
        assert result["sidebar"][0]["icon"] == "home"


# ── PermissionRegistry Advanced ─────────────────────────────────────


class TestPermissionRegistryAdvanced:
    async def test_no_duplicates(self):
        reg = PermissionRegistry()
        reg.add("products.view")
        reg.add("products.view")
        assert reg.all_permissions.count("products.view") == 1

    async def test_multiple_roles_union(self):
        reg = PermissionRegistry()
        reg.add_group("Products", ["products.view", "products.edit"])
        role_map = {"viewer": ["products.view"], "editor": ["products.edit"]}
        perms = reg.get_permissions_for_roles(["viewer", "editor"], role_permission_map=role_map)
        assert "products.view" in perms
        assert "products.edit" in perms

    async def test_groups_list(self):
        reg = PermissionRegistry()
        reg.add_group("Auth", ["auth.login"])
        reg.add_group("Products", ["products.view"])
        assert len(reg.groups) == 2

    async def test_permissions_sorted(self):
        reg = PermissionRegistry()
        reg.add("z.last")
        reg.add("a.first")
        assert reg.all_permissions == ["a.first", "z.last"]


# ── DiscoverModules Advanced ────────────────────────────────────────


class TestDiscoverModulesAdvanced:
    async def test_discover_returns_module_instances(self):
        from simple_module_core.discovery import discover_modules

        modules = discover_modules()
        for mod in modules:
            assert isinstance(mod, ModuleBase)
            assert hasattr(mod, "meta")

    async def test_discover_modules_have_valid_meta(self):
        from simple_module_core.discovery import discover_modules

        modules = discover_modules()
        for mod in modules:
            assert isinstance(mod.meta, ModuleMeta)
            assert isinstance(mod.meta.depends_on, list)
            assert mod.meta.name != ""


# ── discover_modules validation & strict mode ──────────────────────


class _FakeEntryPoint:
    """Minimal EntryPoint shim for testing the validation path.

    Pass a class to return on ``load()``, or a zero-arg callable to
    raise/return something custom (for load-failure cases).
    """

    def __init__(self, name: str, target):
        self.name = name
        self._target = target

    def load(self):
        return (
            self._target()
            if callable(self._target) and not isinstance(self._target, type)
            else self._target
        )


def _patch_entry_points(monkeypatch, eps):
    import simple_module_core.discovery as discovery_mod

    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: eps)


def _boom_loader():
    raise ImportError("boom")


class TestDiscoverModulesValidation:
    async def test_missing_meta_strict_raises(self, monkeypatch):
        class NoMeta(ModuleBase):  # intentionally no meta
            pass

        _patch_entry_points(monkeypatch, [_FakeEntryPoint("nometa", NoMeta)])

        with pytest.raises(InvalidModuleError, match="missing 'meta"):
            discover_modules(strict=True)

    async def test_missing_meta_non_strict_skips(self, monkeypatch):
        class NoMeta(ModuleBase):
            pass

        _patch_entry_points(monkeypatch, [_FakeEntryPoint("nometa", NoMeta)])

        assert discover_modules(strict=False) == []

    async def test_non_modulebase_strict_raises(self, monkeypatch):
        class NotAModule:
            pass

        _patch_entry_points(monkeypatch, [_FakeEntryPoint("notmod", NotAModule)])

        with pytest.raises(InvalidModuleError, match="not a ModuleBase"):
            discover_modules(strict=True)

    async def test_load_failure_strict_raises(self, monkeypatch):
        _patch_entry_points(monkeypatch, [_FakeEntryPoint("broken", _boom_loader)])

        with pytest.raises(InvalidModuleError, match="Failed to load"):
            discover_modules(strict=True)

    async def test_load_failure_non_strict_logs_and_skips(self, monkeypatch, caplog):
        import logging

        _patch_entry_points(monkeypatch, [_FakeEntryPoint("broken", _boom_loader)])

        with caplog.at_level(logging.ERROR, logger="simple_module_core.discovery"):
            modules = discover_modules(strict=False)

        assert modules == []
        assert any("Failed to load" in r.message for r in caplog.records)

    async def test_meta_must_be_modulemeta_instance(self, monkeypatch):
        class BadMeta(ModuleBase):
            meta = "not a ModuleMeta"  # type: ignore[assignment]

        _patch_entry_points(monkeypatch, [_FakeEntryPoint("bad", BadMeta)])

        with pytest.raises(InvalidModuleError, match="missing 'meta"):
            discover_modules(strict=True)


# ── ModuleBase Lifecycle ────────────────────────────────────────────


class TestModuleLifecycle:
    async def test_on_startup_default_noop(self):
        mod = DummyModule()
        await mod.on_startup(None)  # type: ignore

    async def test_on_shutdown_default_noop(self):
        mod = DummyModule()
        await mod.on_shutdown(None)  # type: ignore

    async def test_register_event_handlers_default_noop(self):
        mod = DummyModule()
        bus = EventBus()
        mod.register_event_handlers(bus)

    async def test_register_feature_flags_default_noop(self):
        mod = DummyModule()
        reg = FeatureFlagRegistry()
        mod.register_feature_flags(reg)
        assert len(reg.all_flags) == 0


# ── HealthRegistry ─────────────────────────────────────────────────


class TestHealthRegistry:
    async def test_add_and_list(self):
        reg = HealthRegistry()

        async def check_db() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        reg.add(HealthCheck(name="db", check=check_db))
        assert len(reg.all_checks) == 1
        assert reg.all_checks[0].name == "db"

    async def test_empty_registry(self):
        reg = HealthRegistry()
        assert reg.all_checks == []

    async def test_multiple_checks(self):
        reg = HealthRegistry()

        async def check_a() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        async def check_b() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.DEGRADED, detail="slow")

        reg.add(HealthCheck(name="a", check=check_a))
        reg.add(HealthCheck(name="b", check=check_b))
        assert len(reg.all_checks) == 2

    async def test_check_result_defaults(self):
        result = HealthCheckResult(status=HealthStatus.HEALTHY)
        assert result.detail is None

    async def test_check_result_with_detail(self):
        result = HealthCheckResult(status=HealthStatus.DEGRADED, detail="reindexing")
        assert result.detail == "reindexing"

    async def test_health_status_ordering(self):
        """Verify enum values exist for aggregation logic."""
        assert HealthStatus.HEALTHY == "healthy"
        assert HealthStatus.DEGRADED == "degraded"
        assert HealthStatus.UNHEALTHY == "unhealthy"


class TestModuleNewHooks:
    async def test_register_exception_handlers_default_noop(self):
        mod = DummyModule()
        mod.register_exception_handlers(None)  # type: ignore

    async def test_register_health_checks_default_noop(self):
        mod = DummyModule()
        reg = HealthRegistry()
        mod.register_health_checks(reg)
        assert len(reg.all_checks) == 0

    async def test_register_settings_default_noop(self):
        mod = DummyModule()
        mod.register_settings(None)  # type: ignore


# ── MigrationDiagnostics ──────────────────────────────────────────


class TestMigrationDiagnostics:
    async def test_sm010_migration_mismatch(self):
        """SM010 should fire when current revision != head."""
        diag = MigrationDiagnostics()
        results = diag.check_revision_mismatch(
            current_revision="abc123",
            head_revision="def456",
        )
        assert len(results) == 1
        assert results[0].code == "SM010"
        assert results[0].level == DiagnosticLevel.ERROR

    async def test_sm010_no_error_when_current(self):
        """SM010 should not fire when DB is at head."""
        diag = MigrationDiagnostics()
        results = diag.check_revision_mismatch(
            current_revision="abc123",
            head_revision="abc123",
        )
        assert len(results) == 0

    async def test_sm011_missing_tables(self):
        """SM011 should fire when module tables aren't in migration tables."""
        diag = MigrationDiagnostics()
        results = diag.check_table_coverage(
            module_tables={"products_product", "products_category"},
            migrated_tables={"products_product"},
        )
        assert len(results) == 1
        assert results[0].code == "SM011"
        assert results[0].level == DiagnosticLevel.WARNING
        assert "products_category" in results[0].message

    async def test_sm011_no_warning_when_covered(self):
        """SM011 should not fire when all tables are covered."""
        diag = MigrationDiagnostics()
        results = diag.check_table_coverage(
            module_tables={"products_product"},
            migrated_tables={"products_product"},
        )
        assert len(results) == 0


# ── print_diagnostics ─────────────────────────────────────────────


class TestPrintDiagnostics:
    async def test_writes_to_stderr(self, capsys):
        diag = Diagnostic(
            level=DiagnosticLevel.ERROR,
            code="SM001",
            message="test error",
            module_name="TestMod",
        )
        print_diagnostics([diag])
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "SM001" in captured.err
        assert "Results: 1 error(s)" in captured.err

    async def test_empty_is_quiet(self, capsys):
        print_diagnostics([])
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
