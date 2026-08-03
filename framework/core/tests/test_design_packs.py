"""Tests for the design-pack registry."""

from __future__ import annotations

import pytest

from simple_module_core.design_packs import DesignPack, DesignPackRegistry


def test_registers_and_sorts_by_label():
    registry = DesignPackRegistry()
    registry.register(DesignPack(value="gca", label="Canopy Atlas"))
    registry.register(DesignPack(value="acme", label="Acme"))
    assert [p.value for p in registry.all()] == ["acme", "gca"]
    assert registry.values() == {"acme", "gca"}


def test_duplicate_value_is_an_error():
    # Two modules claiming one root class would silently resolve to whichever
    # stylesheet loaded last, so this has to be loud.
    registry = DesignPackRegistry()
    registry.register(DesignPack(value="gca", label="Canopy Atlas"))
    with pytest.raises(ValueError, match="gca"):
        registry.register(DesignPack(value="gca", label="Other"))


@pytest.mark.parametrize("bad", ["", "-gca", "GCA", "gca root", "gca_root", "gca."])
def test_rejects_values_that_are_not_class_safe(bad):
    registry = DesignPackRegistry()
    with pytest.raises(ValueError):
        registry.register(DesignPack(value=bad, label="X"))


def test_empty_registry_has_no_packs():
    registry = DesignPackRegistry()
    assert registry.all() == []
    assert registry.values() == set()
