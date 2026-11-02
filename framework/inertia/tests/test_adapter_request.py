from __future__ import annotations

from simple_module_inertia.request import InertiaRequest


def test_a_plain_browser_request_is_not_inertia() -> None:
    req = InertiaRequest.from_headers({}, method="GET")
    assert req.is_inertia is False
    assert req.version is None
    assert req.partial_data == frozenset()
    assert req.is_partial_for("Users/Index") is False


def test_every_header_is_parsed_case_insensitively() -> None:
    req = InertiaRequest.from_headers(
        {
            "x-inertia": "true",
            "X-INERTIA-VERSION": "abc",
            "X-Inertia-Partial-Component": "Users/Index",
            "X-Inertia-Partial-Data": "users, roles",
            "X-Inertia-Partial-Except": "stats",
            "X-Inertia-Reset": "users",
            "X-Inertia-Error-Bag": "signup",
            "X-Inertia-Infinite-Scroll-Merge-Intent": "prepend",
            "X-Inertia-Except-Once-Props": "plans,flags",
            "Purpose": "prefetch",
        },
        method="POST",
    )
    assert req.is_inertia is True
    assert req.version == "abc"
    assert req.partial_component == "Users/Index"
    assert req.partial_data == frozenset({"users", "roles"})
    assert req.partial_except == frozenset({"stats"})
    assert req.reset == frozenset({"users"})
    assert req.error_bag == "signup"
    assert req.merge_intent == "prepend"
    assert req.except_once_props == frozenset({"plans", "flags"})
    assert req.is_prefetch is True
    assert req.method == "POST"


def test_partial_only_applies_to_the_named_component() -> None:
    req = InertiaRequest.from_headers(
        {
            "X-Inertia": "true",
            "X-Inertia-Partial-Component": "Users/Index",
            "X-Inertia-Partial-Data": "users",
        },
        method="GET",
    )
    assert req.is_partial_for("Users/Index") is True
    assert req.is_partial_for("Users/Edit") is False


def test_partial_except_alone_still_counts_as_partial() -> None:
    req = InertiaRequest.from_headers(
        {
            "X-Inertia": "true",
            "X-Inertia-Partial-Component": "Feed",
            "X-Inertia-Partial-Except": "ads",
        },
        method="GET",
    )
    assert req.is_partial_for("Feed") is True


def test_unknown_merge_intent_is_ignored() -> None:
    req = InertiaRequest.from_headers(
        {"X-Inertia-Infinite-Scroll-Merge-Intent": "sideways"}, method="GET"
    )
    assert req.merge_intent is None
