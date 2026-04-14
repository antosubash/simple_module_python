"""Tests for module discovery and topological_sort."""

from __future__ import annotations

import logging

import pytest
from simple_module_core.discovery import discover_modules, topological_sort
from simple_module_core.exceptions import CircularDependencyError, InvalidModuleError
from simple_module_core.module import ModuleBase, ModuleMeta


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


class TestDiscoverModules:
    async def test_discover_finds_installed_modules(self):
        """discover_modules() should find modules registered via entry_points."""
        modules = discover_modules()
        names = [m.meta.name for m in modules]
        assert "Products" in names
        assert "Auth" in names
        assert "Dashboard" in names


class TestDiscoverModulesAdvanced:
    async def test_discover_returns_module_instances(self):
        modules = discover_modules()
        for mod in modules:
            assert isinstance(mod, ModuleBase)
            assert hasattr(mod, "meta")

    async def test_discover_modules_have_valid_meta(self):
        modules = discover_modules()
        for mod in modules:
            assert isinstance(mod.meta, ModuleMeta)
            assert isinstance(mod.meta.depends_on, list)
            assert mod.meta.name != ""


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
