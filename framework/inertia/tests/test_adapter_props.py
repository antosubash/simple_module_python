from __future__ import annotations

import warnings

import pytest
from simple_module_inertia.props import (
    Prop,
    ScrollMeta,
    always,
    as_prop,
    deep_merge,
    defer,
    lazy,
    merge,
    once,
    optional,
    prepend,
    resolve_value,
    scroll,
)


def test_as_prop_wraps_a_raw_value_and_passes_a_prop_through() -> None:
    p = as_prop(1)
    assert isinstance(p, Prop) and p.value == 1
    assert as_prop(p) is p


def test_each_factory_sets_exactly_its_flag() -> None:
    assert optional(1).optional is True
    assert always(1).always is True
    assert defer(1).deferred_group == "default"
    assert defer(1, group="sidebar").deferred_group == "sidebar"
    assert merge([]).merge_mode == "append"
    assert prepend([]).merge_mode == "prepend"
    assert deep_merge({}).merge_mode == "deep"
    assert merge([], match_on="data.id").match_on == "data.id"
    assert once(1).once_key is None and once(1).once_expires_at is None
    assert once(1, key="plans", expires_at=1700000000000).once_key == "plans"
    s = scroll([], page_name="page", current_page=1, previous_page=None, next_page=2)
    assert s.scroll == ScrollMeta("page", 1, None, 2, False)


def test_factories_compose_by_stacking_flags() -> None:
    p = merge(defer(lambda: [1], group="feed"), match_on="id")
    assert p.deferred_group == "feed"
    assert p.merge_mode == "append"
    assert p.match_on == "id"
    assert callable(p.value)


def test_lazy_is_a_deprecated_alias_of_optional() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        p = lazy(1)
    assert p.optional is True
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


async def test_resolve_value_handles_values_callables_and_awaitables() -> None:
    async def later() -> str:
        return "async"

    assert await resolve_value(5) == 5
    assert await resolve_value(lambda: "sync") == "sync"
    assert await resolve_value(later) == "async"
    assert await resolve_value(as_prop(lambda: "wrapped")) == "wrapped"


def test_scroll_requires_a_page_name() -> None:
    with pytest.raises(ValueError, match="page_name"):
        scroll([], page_name="", current_page=1, previous_page=None, next_page=None)
