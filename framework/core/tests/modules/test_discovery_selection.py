"""Pre-import entry-point selection and legacy metadata names (#961)."""

import logging
from types import SimpleNamespace

import pytest
from simple_module_core.modules.discovery import discover_modules, topological_sort
from simple_module_core.modules.module import ModuleBase, ModuleMeta
from simple_module_core.runtime.exceptions import InvalidModuleError


class Orders(ModuleBase):
    meta = ModuleMeta(name="Orders")


class Custom(ModuleBase):
    meta = ModuleMeta(name="ArbitraryLegacyName")


class Billing(ModuleBase):
    meta = ModuleMeta(name="Billing")


class Consumer(ModuleBase):
    meta = ModuleMeta(name="Consumer", depends_on=["Orders"])


def _ep(name, target, dist="example", value="example.module:Module"):
    def load():
        if isinstance(target, Exception):
            raise target
        return target

    return SimpleNamespace(
        name=name,
        value=value,
        load=load,
        dist=SimpleNamespace(metadata={"Name": dist}, version="1.0"),
    )


def _install(monkeypatch, *eps):
    monkeypatch.setattr("simple_module_core.modules.discovery.entry_points", lambda group: eps)


def test_disabled_broken_entry_point_never_imports(monkeypatch):
    _install(monkeypatch, _ep("orders", Orders), _ep("broken", ImportError("boom")))
    assert [m.meta.name for m in discover_modules(["EP:ORDERS"], strict=True)] == ["Orders"]


def test_empty_allowlist_never_imports(monkeypatch):
    _install(monkeypatch, _ep("broken", ImportError("boom")))
    assert discover_modules([], strict=True) == []


def test_enabled_broken_entry_point_still_fails(monkeypatch):
    _install(monkeypatch, _ep("broken", ImportError("boom")))
    with pytest.raises(InvalidModuleError, match="boom"):
        discover_modules(["ep:broken"], strict=True)


def test_entry_point_name_selects_a_different_meta_name(monkeypatch, caplog):
    _install(monkeypatch, _ep("custom_package", Custom))
    assert [m.meta.name for m in discover_modules(["EP:CUSTOM_PACKAGE"])] == ["ArbitraryLegacyName"]
    assert "not installed" not in caplog.text


@pytest.mark.parametrize("enabled", [["ArbitraryLegacyName"], ["ep:orders", "arbitrarylegacyname"]])
def test_meta_names_and_mixed_allowlists_remain_supported(monkeypatch, enabled):
    _install(monkeypatch, _ep("orders", Orders), _ep("custom_package", Custom))
    names = [m.meta.name for m in discover_modules(enabled, strict=True)]
    assert "ArbitraryLegacyName" in names
    assert ("Orders" in names) == (len(enabled) == 2)


def test_unknown_meta_names_do_not_guess_which_plugin_to_skip(monkeypatch):
    _install(monkeypatch, _ep("broken", ImportError("boom")))
    with pytest.raises(InvalidModuleError, match="boom"):
        discover_modules(["ArbitraryLegacyName"], strict=True)


@pytest.mark.parametrize("enabled", [["Orders"], ["Orders", "Consumer"]])
def test_metadata_name_collision_preserves_selection_and_dependencies(monkeypatch, enabled):
    _install(
        monkeypatch,
        _ep("orders_plugin", Orders),
        _ep("orders", Billing),
        _ep("consumer", Consumer),
    )
    modules = topological_sort(discover_modules(enabled, strict=True), strict=True)
    assert [m.meta.name for m in modules] == enabled


def test_unqualified_entry_point_name_does_not_select_metadata(monkeypatch, caplog):
    _install(monkeypatch, _ep("custom_package", Custom))
    assert discover_modules(["custom_package"], strict=True) == []
    assert "custom_package" in caplog.text and "not installed" in caplog.text


def test_explicit_entry_point_disambiguates_metadata_collision(monkeypatch):
    _install(monkeypatch, _ep("orders_plugin", Orders), _ep("orders", Billing))
    assert [m.meta.name for m in discover_modules(["ep:orders"], strict=True)] == ["Billing"]


@pytest.mark.parametrize("enabled", [["ep:absent"], ["Orders", "ep:absent"], ["ep:"]])
def test_unknown_explicit_entry_point_fails_strict_discovery(monkeypatch, enabled):
    _install(monkeypatch, _ep("orders", Orders))
    with pytest.raises(InvalidModuleError, match=r"ep:.*not installed"):
        discover_modules(enabled, strict=True)


def test_unknown_explicit_entry_point_warns_in_development(monkeypatch, caplog):
    _install(monkeypatch, _ep("orders", Orders), _ep("broken", ImportError("boom")))
    with caplog.at_level(logging.WARNING):
        assert [m.meta.name for m in discover_modules(["ep:orders", "ep:absent"])] == ["Orders"]
    assert "ep:absent" in caplog.text and "not installed" in caplog.text
    assert "boom" not in caplog.text


def test_mixed_selectors_still_load_candidates_for_metadata_names(monkeypatch):
    _install(monkeypatch, _ep("orders", Orders), _ep("broken", ImportError("boom")))
    with pytest.raises(InvalidModuleError, match="boom"):
        discover_modules(["ep:orders", "ArbitraryLegacyName"], strict=True)


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
    assert len(discover_modules(["ep:first"], strict=True)) == 1


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("first_key", "second_key"),
    [
        (("a-dist", "z", "z:Module"), ("b-dist", "a", "a:Module")),
        (("same-dist", "a", "z:Module"), ("same-dist", "b", "a:Module")),
        (("same-dist", "same", "a:Module"), ("same-dist", "same", "b:Module")),
    ],
)
def test_duplicate_winner_is_independent_of_enumeration(
    monkeypatch, reverse, first_key, second_key
):
    class OtherOrders(ModuleBase):
        meta = ModuleMeta(name="Orders")

    first_dist, first_name, first_value = first_key
    second_dist, second_name, second_value = second_key
    eps = [
        _ep(first_name, Orders, first_dist, first_value),
        _ep(second_name, OtherOrders, second_dist, second_value),
    ]
    _install(monkeypatch, *(reversed(eps) if reverse else eps))
    (module,) = discover_modules()
    assert type(module) is Orders


def test_topological_sort_rejects_duplicate_names_in_strict_mode():
    with pytest.raises(InvalidModuleError, match="SM008"):
        topological_sort([Orders(), Orders()], strict=True)


def test_topological_sort_warns_and_keeps_first_duplicate(caplog):
    first = Orders()
    with caplog.at_level(logging.WARNING):
        assert topological_sort([first, Orders()]) == [first]
    assert "SM008" in caplog.text
