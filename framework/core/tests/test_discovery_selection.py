"""Pre-import entry-point selection and legacy metadata names (#961)."""

import logging
from types import SimpleNamespace

import pytest
from simple_module_core.discovery import discover_modules, topological_sort
from simple_module_core.exceptions import InvalidModuleError
from simple_module_core.module import ModuleBase, ModuleMeta


class Orders(ModuleBase):
    meta = ModuleMeta(name="Orders")


class Custom(ModuleBase):
    meta = ModuleMeta(name="ArbitraryLegacyName")


def _ep(name, target, dist="example"):
    def load():
        if isinstance(target, Exception):
            raise target
        return target

    return SimpleNamespace(
        name=name, load=load, dist=SimpleNamespace(metadata={"Name": dist}, version="1.0")
    )


def _install(monkeypatch, *eps):
    monkeypatch.setattr("simple_module_core.discovery.entry_points", lambda group: eps)


def test_disabled_broken_entry_point_never_imports(monkeypatch):
    _install(monkeypatch, _ep("orders", Orders), _ep("broken", ImportError("boom")))
    assert [m.meta.name for m in discover_modules(["ORDERS"], strict=True)] == ["Orders"]


def test_empty_allowlist_never_imports(monkeypatch):
    _install(monkeypatch, _ep("broken", ImportError("boom")))
    assert discover_modules([], strict=True) == []


def test_enabled_broken_entry_point_still_fails(monkeypatch):
    _install(monkeypatch, _ep("broken", ImportError("boom")))
    with pytest.raises(InvalidModuleError, match="boom"):
        discover_modules(["broken"], strict=True)


def test_entry_point_name_selects_a_different_meta_name(monkeypatch, caplog):
    _install(monkeypatch, _ep("custom_package", Custom))
    assert [m.meta.name for m in discover_modules(["CUSTOM_PACKAGE"])] == ["ArbitraryLegacyName"]
    assert "not installed" not in caplog.text


@pytest.mark.parametrize("enabled", [["ArbitraryLegacyName"], ["orders", "arbitrarylegacyname"]])
def test_meta_names_and_mixed_allowlists_remain_supported(monkeypatch, enabled):
    _install(monkeypatch, _ep("orders", Orders), _ep("custom_package", Custom))
    names = [m.meta.name for m in discover_modules(enabled, strict=True)]
    assert "ArbitraryLegacyName" in names
    assert ("Orders" in names) == (len(enabled) == 2)


def test_unknown_meta_names_do_not_guess_which_plugin_to_skip(monkeypatch):
    _install(monkeypatch, _ep("broken", ImportError("boom")))
    with pytest.raises(InvalidModuleError, match="boom"):
        discover_modules(["ArbitraryLegacyName"], strict=True)


def test_ci_style_meta_name_list_keeps_multiword_modules():
    enabled = ["Auth", "Users", "BackgroundTasks", "FileStorage", "FeatureFlags", "AuditLog"]
    assert {m.meta.name for m in discover_modules(enabled, strict=True)} == set(enabled)


def test_duplicate_names_fail_strict_with_both_distributions(monkeypatch):
    _install(monkeypatch, _ep("first", Orders, "first-dist"), _ep("second", Orders, "second-dist"))
    with pytest.raises(InvalidModuleError, match="SM008") as caught:
        discover_modules(strict=True)
    assert all(name in str(caught.value) for name in ("Orders", "first-dist", "second-dist"))


def test_duplicate_names_warn_in_development_and_keep_first(monkeypatch, caplog):
    _install(monkeypatch, _ep("first", Orders, "first-dist"), _ep("second", Orders, "second-dist"))
    with caplog.at_level(logging.WARNING):
        modules = discover_modules()
    assert [m.meta.name for m in modules] == ["Orders"]
    assert all(name in caplog.text for name in ("SM008", "Orders", "first-dist", "second-dist"))


def test_disabled_duplicate_does_not_conflict(monkeypatch):
    _install(monkeypatch, _ep("first", Orders), _ep("second", Orders))
    assert len(discover_modules(["first"], strict=True)) == 1


def test_topological_sort_rejects_duplicate_names_in_strict_mode():
    with pytest.raises(InvalidModuleError, match="SM008"):
        topological_sort([Orders(), Orders()], strict=True)


def test_topological_sort_warns_and_keeps_first_duplicate(caplog):
    first = Orders()
    with caplog.at_level(logging.WARNING):
        assert topological_sort([first, Orders()]) == [first]
    assert "SM008" in caplog.text
