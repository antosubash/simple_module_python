"""Merge / once / scroll metadata — what the page object announces alongside props."""

from __future__ import annotations

from simple_module_inertia.props import deep_merge, defer, merge, once, prepend, scroll
from simple_module_inertia.request import InertiaRequest
from simple_module_inertia.resolve import resolve_props

COMPONENT = "Feed/Index"


def _req(**headers: str) -> InertiaRequest:
    return InertiaRequest.from_headers({"X-Inertia": "true", **headers}, method="GET")


async def test_each_merge_mode_is_reported_under_its_own_key() -> None:
    out = await resolve_props(
        {
            "posts": merge([1]),
            "notices": prepend([2]),
            "settings": deep_merge({"a": 1}),
        },
        {},
        COMPONENT,
        _req(),
    )
    assert out.merge == ["posts"]
    assert out.prepend == ["notices"]
    assert out.deep_merge == ["settings"]
    assert out.match_on == []


async def test_match_on_is_reported_as_prop_path_dot_key() -> None:
    out = await resolve_props(
        {"conversations": merge({"data": []}, match_on="data.id")}, {}, COMPONENT, _req()
    )
    assert out.match_on == ["conversations.data.id"]


async def test_a_reset_key_is_resolved_but_not_reported_as_mergeable() -> None:
    out = await resolve_props(
        {"posts": merge([1]), "notices": prepend([2])},
        {},
        COMPONENT,
        _req(**{"X-Inertia-Reset": "posts"}),
    )
    assert out.props == {"posts": [1], "notices": [2]}
    assert out.merge == []
    assert out.prepend == ["notices"]


async def test_a_deferred_prop_can_also_be_mergeable() -> None:
    full = await resolve_props({"feed": merge(defer(lambda: [1]))}, {}, COMPONENT, _req())
    assert full.props == {} and full.deferred == {"default": ["feed"]}
    assert full.merge == ["feed"], "merge strategy is announced up front"

    partial = await resolve_props(
        {"feed": merge(defer(lambda: [1]))},
        {},
        COMPONENT,
        _req(**{"X-Inertia-Partial-Component": COMPONENT, "X-Inertia-Partial-Data": "feed"}),
    )
    assert partial.props == {"feed": [1]} and partial.merge == ["feed"]


async def test_once_key_defaults_to_the_prop_name_and_carries_expiry() -> None:
    out = await resolve_props(
        {
            "plans": once(["a"]),
            "flags": once(["b"], key="feature-flags", expires_at=1700000000000),
        },
        {},
        COMPONENT,
        _req(),
    )
    assert out.once == {
        "plans": {"prop": "plans", "expiresAt": None},
        "feature-flags": {"prop": "flags", "expiresAt": 1700000000000},
    }


async def test_scroll_props_report_cursor_metadata() -> None:
    out = await resolve_props(
        {
            "posts": scroll(
                [1, 2], page_name="page", current_page=1, previous_page=None, next_page=2
            )
        },
        {},
        COMPONENT,
        _req(),
    )
    assert out.props == {"posts": [1, 2]}
    assert out.scroll == {
        "posts": {
            "pageName": "page",
            "currentPage": 1,
            "previousPage": None,
            "nextPage": 2,
            "reset": False,
        }
    }
    assert out.merge == ["posts"], "scroll props merge by default so pages accumulate"


async def test_scroll_merge_intent_prepend_moves_the_key() -> None:
    out = await resolve_props(
        {"posts": scroll([0], page_name="page", current_page=0, previous_page=None, next_page=1)},
        {},
        COMPONENT,
        _req(**{"X-Inertia-Infinite-Scroll-Merge-Intent": "prepend"}),
    )
    assert out.prepend == ["posts"] and out.merge == []
