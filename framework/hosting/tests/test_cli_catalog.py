"""Tests for the module catalog and dependency expansion."""

from __future__ import annotations

import pytest

from simple_module_hosting.cli.catalog import (
    CATALOG,
    PRESETS,
    ModuleEntry,
    expand_deps,
)


def test_catalog_keys_match_entry_names() -> None:
    for key, entry in CATALOG.items():
        assert key == entry.name, f"catalog key {key!r} != entry.name {entry.name!r}"


def test_every_requires_value_is_a_known_catalog_key() -> None:
    for entry in CATALOG.values():
        for required in entry.requires:
            assert required in CATALOG, (
                f"{entry.name} requires unknown module {required!r}"
            )


def test_presets_only_reference_known_modules() -> None:
    for name, mods in PRESETS.items():
        for m in mods:
            assert m in CATALOG, f"preset {name!r} references unknown module {m!r}"


def test_expand_deps_returns_input_when_no_requires() -> None:
    resolved, added = expand_deps(["auth"])
    assert resolved == ["auth"]
    assert added == []


def test_expand_deps_pulls_in_transitive_dep() -> None:
    resolved, added = expand_deps(["users"])
    assert set(resolved) == {"auth", "users"}
    assert added == [("auth", "users")]


def test_expand_deps_pulls_in_chain() -> None:
    resolved, added = expand_deps(["datasets"])
    assert set(resolved) == {
        "datasets",
        "file_storage",
        "settings",
        "background_tasks",
        "users",
        "auth",
    }
    added_names = {a for a, _ in added}
    assert added_names == {"file_storage", "settings", "background_tasks", "users", "auth"}


def test_expand_deps_idempotent_when_input_already_complete() -> None:
    resolved1, _ = expand_deps(["users"])
    resolved2, added2 = expand_deps(resolved1)
    assert sorted(resolved1) == sorted(resolved2)
    assert added2 == []


def test_expand_deps_unknown_name_raises_with_available_list() -> None:
    with pytest.raises(KeyError) as exc:
        expand_deps(["does_not_exist"])
    msg = str(exc.value)
    assert "does_not_exist" in msg
    assert "auth" in msg


def test_expand_deps_preserves_load_order_dep_before_dependent() -> None:
    resolved, _ = expand_deps(["dashboard"])
    for i, name in enumerate(resolved):
        for required in CATALOG[name].requires:
            assert resolved.index(required) < i, (
                f"{required} must appear before {name} in {resolved}"
            )


def test_module_entry_is_frozen() -> None:
    entry = ModuleEntry(name="x", package="simple_module_x", display="X")
    with pytest.raises(Exception):
        entry.name = "y"  # type: ignore[misc]
