"""Tests for simple_module_core.deprecation and the legacy public-paths bridge."""

from __future__ import annotations

import pytest
from simple_module_core.deprecation import (
    deprecate,
    deprecated,
    expired_deprecations,
    registered_deprecations,
)
from simple_module_core.public_routes import legacy_provider_public_paths


def test_function_warns_and_registers() -> None:
    @deprecated(remove_in="9.9.9", use="new()", name="tests.old_fn")
    def old_fn(x: int) -> int:
        return x + 1

    with pytest.warns(DeprecationWarning, match=r"tests\.old_fn.*9\.9\.9.*new\(\)"):
        assert old_fn(1) == 2
    assert any(d.name == "tests.old_fn" for d in registered_deprecations())


def test_class_warns_on_instantiation() -> None:
    @deprecated(remove_in="9.9.9", name="tests.OldCls")
    class OldCls:
        def __init__(self, v: int) -> None:
            self.v = v

    with pytest.warns(DeprecationWarning, match=r"tests\.OldCls"):
        assert OldCls(3).v == 3


def test_expiry_compares_against_remove_in() -> None:
    deprecate("tests.expiry", remove_in="1.2.0")
    names = lambda v: {d.name for d in expired_deprecations(v)}  # noqa: E731
    assert "tests.expiry" not in names("1.1.9")
    assert "tests.expiry" in names("1.2.0")
    # A pre-release of the removal version counts as reaching it.
    assert "tests.expiry" in names("1.2.0rc1")


def test_invalid_remove_in_fails_at_registration() -> None:
    with pytest.raises(ValueError, match=r"[Ii]nvalid"):
        deprecate("tests.bad", remove_in="soon")


def test_legacy_public_paths_warns_once_per_provider_class() -> None:
    class Legacy:
        def get_public_paths(self):
            return (("/x",), ("/y",))

    with pytest.warns(DeprecationWarning, match="get_public_paths"):
        assert legacy_provider_public_paths(Legacy()) == (("/x",), ("/y",))


def test_provider_without_the_method_yields_nothing() -> None:
    assert legacy_provider_public_paths(object()) == ((), ())
