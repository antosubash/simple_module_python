"""Tests for DesignPackRegistry — modules contribute site-wide design packs.

A design pack is a stylesheet a module ships that restyles the public site by
overriding the base tokens beneath a ``<value>-root`` class. The registry is
what lets branding offer an administrator only the packs an installed module
actually provides: selecting one nothing ships would put a class on the
document with no stylesheet behind it, silently doing nothing.

The registry supplies the dropdown, not the stylesheet — a pack's CSS still
reaches the bundle through the host's ``styles.css``.
"""

from __future__ import annotations

import dataclasses

import pytest
from simple_module_core.design_packs import DesignPack, DesignPackRegistry


class TestDesignPack:
    def test_carries_slug_and_label(self):
        pack = DesignPack(value="gca", label="Canopy Atlas")
        assert pack.value == "gca"
        assert pack.label == "Canopy Atlas"

    def test_is_frozen(self):
        pack = DesignPack(value="gca", label="Canopy Atlas")
        with pytest.raises(dataclasses.FrozenInstanceError):
            pack.value = "other"

    @pytest.mark.parametrize("value", ["gca", "g", "7", "canopy-atlas", "a1-b2"])
    def test_accepts_a_css_safe_slug(self, value):
        assert DesignPack(value=value, label="X").value == value

    @pytest.mark.parametrize(
        "value",
        ["", "-gca", "GCA", "canopy_atlas", "canopy atlas", "gca!", "gca.pack"],
    )
    def test_rejects_a_slug_that_would_not_survive_a_class_name(self, value):
        # The site root class is f"{value}-root", so anything that isn't a bare
        # lowercase CSS identifier fragment either fails to select or, worse,
        # silently selects something else.
        with pytest.raises(ValueError, match="value"):
            DesignPack(value=value, label="X")


class TestDesignPackRegistry:
    def test_starts_empty(self):
        assert DesignPackRegistry().all() == []

    def test_registered_pack_is_returned(self):
        registry = DesignPackRegistry()
        pack = DesignPack(value="gca", label="Canopy Atlas")
        registry.register(pack)
        assert registry.all() == [pack]

    def test_all_preserves_registration_order(self):
        registry = DesignPackRegistry()
        first = DesignPack(value="gca", label="Canopy Atlas")
        second = DesignPack(value="aurora", label="Aurora")
        registry.register(first)
        registry.register(second)
        assert registry.all() == [first, second]

    def test_all_returns_a_copy(self):
        registry = DesignPackRegistry()
        registry.register(DesignPack(value="gca", label="Canopy Atlas"))
        registry.all().clear()
        assert len(registry.all()) == 1

    def test_duplicate_value_is_rejected(self):
        # Two modules claiming one root class would leave whichever stylesheet
        # loaded last in charge — a silent overwrite is the wrong answer.
        registry = DesignPackRegistry()
        registry.register(DesignPack(value="gca", label="Canopy Atlas"))
        with pytest.raises(ValueError, match="gca"):
            registry.register(DesignPack(value="gca", label="Someone Else's Pack"))

    def test_distinct_values_sharing_a_label_are_allowed(self):
        registry = DesignPackRegistry()
        registry.register(DesignPack(value="gca", label="Atlas"))
        registry.register(DesignPack(value="gca-dark", label="Atlas"))
        assert [p.value for p in registry.all()] == ["gca", "gca-dark"]

    def test_has_reports_membership(self):
        # Branding's PUT validates the submitted slug against this.
        registry = DesignPackRegistry()
        registry.register(DesignPack(value="gca", label="Canopy Atlas"))
        assert registry.has("gca")
        assert not registry.has("aurora")

    def test_has_is_false_on_an_empty_registry(self):
        assert not DesignPackRegistry().has("gca")


class TestPublicSurface:
    def test_both_names_are_exported_from_the_package_root(self):
        # Module authors import registries from ``simple_module_core``, the
        # same way they reach MenuRegistry or PublicRouteRegistry.
        import simple_module_core

        assert simple_module_core.DesignPack is DesignPack
        assert simple_module_core.DesignPackRegistry is DesignPackRegistry
        assert {"DesignPack", "DesignPackRegistry"} <= set(simple_module_core.__all__)
