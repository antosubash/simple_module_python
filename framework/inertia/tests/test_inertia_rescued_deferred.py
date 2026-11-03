"""Rescued deferred failures leave other props usable (#773)."""

import logging

import pytest
from simple_module_inertia.page import build_page
from simple_module_inertia.props import defer, merge, once
from simple_module_inertia.request import InertiaRequest
from simple_module_inertia.resolve import resolve_props


def broken():
    raise RuntimeError("analytics backend down")


async def broken_async():
    raise RuntimeError("analytics backend down")


def request(partial=True):
    headers = {"X-Inertia": "true"}
    if partial:
        headers.update(
            {"X-Inertia-Partial-Component": "Page", "X-Inertia-Partial-Data": "analytics,user"}
        )
    return InertiaRequest.from_headers(headers, method="GET")


@pytest.mark.parametrize("loader", [broken, broken_async])
async def test_rescued_failure_omits_prop_and_preserves_other_values(loader):
    out = await resolve_props(
        {"analytics": defer(loader, rescue=True), "user": "j"}, {}, "Page", request()
    )
    assert out.props == {"user": "j"}


async def test_rescued_failure_is_announced_in_page():
    out = await resolve_props({"analytics": defer(broken, rescue=True)}, {}, "Page", request())
    page = build_page(component="Page", resolved=out, url="/", version="v", errors={})
    assert page["rescuedProps"] == ["analytics"]


async def test_rescued_failure_logs_exception(caplog):
    with caplog.at_level(logging.ERROR):
        await resolve_props({"analytics": defer(broken, rescue=True)}, {}, "Page", request())
    assert any(
        record.name == "simple_module_inertia.resolve"
        and record.exc_info
        and "analytics backend down" in str(record.exc_info[1])
        for record in caplog.records
    )


async def test_non_rescued_failure_still_raises():
    with pytest.raises(RuntimeError, match="analytics backend down"):
        await resolve_props({"analytics": defer(broken)}, {}, "Page", request())


async def test_rescued_deferred_is_not_evaluated_on_full_visit():
    out = await resolve_props(
        {"analytics": defer(broken, group="stats", rescue=True)}, {}, "Page", request(False)
    )
    assert out.deferred == {"stats": ["analytics"]}


async def test_full_visit_does_not_announce_rescued_props():
    out = await resolve_props({"analytics": defer(broken, rescue=True)}, {}, "Page", request(False))
    page = build_page(component="Page", resolved=out, url="/", version="v", errors={})
    assert "rescuedProps" not in page


async def test_rescued_failure_keeps_merge_and_once_flags_composable():
    out = await resolve_props(
        {"analytics": once(merge(defer(broken, rescue=True)))}, {}, "Page", request()
    )
    assert out.rescued == ["analytics"]


async def test_rescued_failure_does_not_announce_success_metadata():
    out = await resolve_props(
        {"analytics": once(merge(defer(broken, rescue=True)))}, {}, "Page", request()
    )
    assert (out.merge, out.once) == ([], {})


async def test_nested_rescued_prop_reports_dotted_path():
    req = InertiaRequest.from_headers(
        {"X-Inertia-Partial-Component": "Page", "X-Inertia-Partial-Data": "stats"}, method="GET"
    )
    out = await resolve_props(
        {"stats": {"analytics": defer(broken, rescue=True), "count": 1}}, {}, "Page", req
    )
    assert out.rescued == ["stats.analytics"]
