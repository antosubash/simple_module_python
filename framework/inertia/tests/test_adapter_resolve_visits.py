"""Full-visit vs partial-reload rules — the spec's §3, one test per rule."""

from __future__ import annotations

from simple_module_inertia.props import always, defer, once, optional
from simple_module_inertia.request import InertiaRequest
from simple_module_inertia.resolve import resolve_props

COMPONENT = "Users/Index"


def _req(method: str = "GET", **headers: str) -> InertiaRequest:
    h = {"X-Inertia": "true", **headers}
    return InertiaRequest.from_headers(h, method=method)


def _partial(data: str = "", exclude: str = "", component: str = COMPONENT, **extra: str):
    headers = {"X-Inertia-Partial-Component": component, **extra}
    if data:
        headers["X-Inertia-Partial-Data"] = data
    if exclude:
        headers["X-Inertia-Partial-Except"] = exclude
    return _req(**headers)


async def test_full_visit_resolves_regular_and_skips_optional_and_deferred() -> None:
    out = await resolve_props(
        {"users": [1], "stats": optional(lambda: {"n": 1}), "feed": defer(lambda: [2])},
        {},
        COMPONENT,
        _req(),
    )
    assert out.props == {"users": [1]}
    assert out.deferred == {"default": ["feed"]}


async def test_full_visit_resolves_always_props() -> None:
    out = await resolve_props({"flash": always(lambda: "hi")}, {}, COMPONENT, _req())
    assert out.props == {"flash": "hi"}


async def test_partial_data_resolves_only_the_named_keys_plus_always() -> None:
    out = await resolve_props(
        {"users": [1], "roles": [2], "flash": always("x"), "feed": defer(lambda: [3])},
        {},
        COMPONENT,
        _partial(data="users"),
    )
    assert out.props == {"users": [1], "flash": "x"}
    assert out.deferred == {}, "deferred metadata is only announced on full visits"


async def test_partial_data_resolves_optional_and_deferred_when_named() -> None:
    out = await resolve_props(
        {"stats": optional(lambda: {"n": 1}), "feed": defer(lambda: [3])},
        {},
        COMPONENT,
        _partial(data="stats,feed"),
    )
    assert out.props == {"stats": {"n": 1}, "feed": [3]}


async def test_partial_except_drops_the_named_keys() -> None:
    out = await resolve_props(
        {"users": [1], "roles": [2], "stats": [3]}, {}, COMPONENT, _partial(exclude="stats")
    )
    assert out.props == {"users": [1], "roles": [2]}


async def test_partial_data_and_except_combine() -> None:
    out = await resolve_props(
        {"users": [1], "roles": [2], "stats": [3]},
        {},
        COMPONENT,
        _partial(data="users,stats", exclude="stats"),
    )
    assert out.props == {"users": [1]}


async def test_partial_for_another_component_is_a_full_visit() -> None:
    out = await resolve_props(
        {"users": [1], "stats": optional(lambda: 1)},
        {},
        COMPONENT,
        _partial(data="stats", component="Users/Edit"),
    )
    assert out.props == {"users": [1]}


async def test_once_props_are_skipped_when_the_client_already_has_them() -> None:
    out = await resolve_props(
        {"plans": once(lambda: ["a"]), "flags": once(lambda: ["b"])},
        {},
        COMPONENT,
        _req(**{"X-Inertia-Except-Once-Props": "plans"}),
    )
    assert out.props == {"flags": ["b"]}
    assert out.once == {"flags": {"prop": "flags", "expiresAt": None}}


async def test_shared_props_merge_under_page_props() -> None:
    out = await resolve_props(
        {"title": "page"}, {"title": "shared", "auth": {"id": 1}}, COMPONENT, _req()
    )
    assert out.props == {"title": "page", "auth": {"id": 1}}
    assert out.shared == ["auth"]


async def test_callables_and_awaitables_resolve_inside_nested_containers() -> None:
    async def later() -> int:
        return 2

    out = await resolve_props(
        {"nested": {"a": lambda: 1, "b": [later, {"c": lambda: 3}]}}, {}, COMPONENT, _req()
    )
    assert out.props == {"nested": {"a": 1, "b": [2, {"c": 3}]}}
