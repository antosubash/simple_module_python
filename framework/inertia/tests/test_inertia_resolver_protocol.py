"""Once, merge and scroll regressions for issues #768-#771."""

import pytest
from simple_module_inertia.props import deep_merge, defer, merge, once, optional, prepend, scroll
from simple_module_inertia.request import InertiaRequest
from simple_module_inertia.resolve import resolve_props


def request(**headers):
    return InertiaRequest.from_headers({"X-Inertia": "true", **headers}, method="GET")


def partial(only="", exclude="", **headers):
    return request(
        **{
            "X-Inertia-Partial-Component": "Page",
            "X-Inertia-Partial-Data": only,
            "X-Inertia-Partial-Except": exclude,
            **headers,
        }
    )


async def test_cached_once_keeps_metadata_without_running_loader():
    def broken():
        pytest.fail("Cached loader must not run")

    out = await resolve_props(
        {"plans": once(broken)},
        {},
        "Page",
        request(**{"X-Inertia-Except-Once-Props": "plans"}),
    )
    assert out.once == {"plans": {"prop": "plans", "expiresAt": None}}


async def test_partial_once_ignores_client_cache_and_announces_value():
    out = await resolve_props(
        {"plans": once(lambda: ["basic", "pro"])},
        {},
        "Page",
        partial("plans", **{"X-Inertia-Except-Once-Props": "plans"}),
    )
    assert out.props == {"plans": ["basic", "pro"]}
    assert out.once == {"plans": {"prop": "plans", "expiresAt": None}}


@pytest.mark.parametrize(
    "factory,field",
    [(merge, "merge"), (prepend, "prepend"), (deep_merge, "deep_merge"), (once, "once")],
)
@pytest.mark.parametrize("req", [partial("user"), partial(exclude="posts")])
async def test_partial_omits_unselected_metadata(factory, field, req):
    out = await resolve_props({"posts": factory(lambda: [1]), "user": "j"}, {}, "Page", req)
    assert not getattr(out, field)


async def test_partial_omits_unselected_match_metadata():
    out = await resolve_props(
        {"posts": merge(list, match_on="id"), "user": "j"},
        {},
        "Page",
        partial("user"),
    )
    assert out.match_on == []


@pytest.mark.parametrize("wrapper", [defer, optional])
async def test_full_visit_keeps_unresolved_merge_metadata(wrapper):
    out = await resolve_props({"posts": merge(wrapper(lambda: [1]))}, {}, "Page", request())
    assert out.merge == ["posts"]


@pytest.mark.parametrize("wrapper", [defer, optional])
async def test_full_visit_keeps_unresolved_once_metadata(wrapper):
    out = await resolve_props({"plans": once(wrapper(lambda: [1]))}, {}, "Page", request())
    assert out.once == {"plans": {"prop": "plans", "expiresAt": None}}


def posts(**kwargs):
    return scroll(
        {"data": [{"id": 1}], "meta": {"total": 40}},
        page_name="page",
        current_page=1,
        previous_page=None,
        next_page=2,
        **kwargs,
    )


@pytest.mark.parametrize("intent,field", [("append", "merge"), ("prepend", "prepend")])
@pytest.mark.parametrize(
    "kwargs,path",
    [({}, "posts.data"), ({"wrapper": "items"}, "posts.items"), ({"wrapper": None}, "posts")],
)
async def test_scroll_labels_wrapper_by_merge_intent(intent, field, kwargs, path):
    out = await resolve_props(
        {"posts": posts(**kwargs)},
        {},
        "Page",
        request(**{"X-Inertia-Infinite-Scroll-Merge-Intent": intent}),
    )
    assert getattr(out, field) == [path]


@pytest.mark.parametrize(
    "explicit,header", [(False, True), (True, False), (True, True), (False, False)]
)
async def test_scroll_reset_combines_header_and_explicit_flag(explicit, header):
    out = await resolve_props(
        {"posts": posts(reset=explicit)},
        {},
        "Page",
        partial("posts", **{"X-Inertia-Reset": "posts" if header else ""}),
    )
    assert out.scroll["posts"]["reset"] is (explicit or header)


@pytest.mark.parametrize("explicit,header", [(False, True), (True, False)])
async def test_reset_scroll_has_no_merge_label(explicit, header):
    out = await resolve_props(
        {"posts": posts(reset=explicit)},
        {},
        "Page",
        partial("posts", **{"X-Inertia-Reset": "posts" if header else ""}),
    )
    assert out.merge == []
