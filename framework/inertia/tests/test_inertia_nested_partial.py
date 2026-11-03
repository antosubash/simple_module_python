"""Dotted partial paths filter plain dictionaries before evaluation (#772)."""

import pytest
from simple_module_inertia.props import always, merge, once, optional
from simple_module_inertia.request import InertiaRequest
from simple_module_inertia.resolve import resolve_props


def partial(only="", exclude=""):
    return InertiaRequest.from_headers(
        {
            "X-Inertia": "true",
            "X-Inertia-Partial-Component": "Page",
            "X-Inertia-Partial-Data": only,
            "X-Inertia-Partial-Except": exclude,
        },
        method="GET",
    )


@pytest.mark.parametrize(
    "only,exclude,expected",
    [
        ("auth.user", "", {"auth": {"user": {"name": "J"}}}),
        ("", "auth.permissions", {"auth": {"user": {"name": "J"}}, "author": 2}),
        ("auth", "auth.permissions", {"auth": {"user": {"name": "J"}}}),
        ("auth.user.name", "", {"auth": {"user": {"name": "J"}}}),
        ("auth.user", "auth", {}),
        ("auth", "", {"auth": {"user": {"name": "J"}, "permissions": ["a"]}}),
    ],
)
async def test_nested_paths_select_and_exclude_subtrees(only, exclude, expected):
    out = await resolve_props(
        {"auth": {"user": {"name": "J"}, "permissions": ["a"]}, "author": 2},
        {},
        "Page",
        partial(only, exclude),
    )
    assert out.props == expected


async def test_excluded_nested_loader_never_runs():
    def broken():
        pytest.fail("Excluded nested loader must not run")

    out = await resolve_props(
        {"auth": {"user": "J", "permissions": broken}, "stats": optional(broken)},
        {},
        "Page",
        partial("auth.user"),
    )
    assert out.props == {"auth": {"user": "J"}}


@pytest.mark.parametrize("kind", ["callable", "awaitable", "prop", "always"])
async def test_resolved_values_bypass_child_filters(kind):
    value = {"user": {"name": lambda: "J"}, "permissions": ["a"]}

    async def later():
        return value

    raw = {
        "callable": lambda: value,
        "awaitable": later,
        "prop": optional(value),
        "always": always(value),
    }[kind]
    if kind == "awaitable":
        raw = later()
    out = await resolve_props({"auth": raw}, {}, "Page", partial("auth.user", "auth.permissions"))
    assert out.props == {"auth": {"user": {"name": "J"}, "permissions": ["a"]}}


async def test_always_bypasses_exclusion_of_its_own_path():
    out = await resolve_props({"auth": always({"user": "J"})}, {}, "Page", partial(exclude="auth"))
    assert out.props == {"auth": {"user": "J"}}


async def test_nested_merge_metadata_uses_selected_path():
    out = await resolve_props(
        {"auth": {"users": merge([1], match_on="id"), "plans": once([2])}},
        {},
        "Page",
        partial("auth.users"),
    )
    assert out.match_on == ["auth.users.id"]


async def test_nested_once_metadata_uses_selected_path():
    out = await resolve_props(
        {"auth": {"users": merge([1]), "plans": once([2])}}, {}, "Page", partial("auth.plans")
    )
    assert out.once == {"auth.plans": {"prop": "auth.plans", "expiresAt": None}}


async def test_metadata_only_filter_does_not_treat_ancestor_as_selected():
    out = await resolve_props(
        {"auth": once(merge({"user": "J"}, match_on="id"))}, {}, "Page", partial("auth.user")
    )
    assert (out.merge, out.match_on, out.once) == ([], [], {})
