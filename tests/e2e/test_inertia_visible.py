import pytest
from playwright.sync_api import expect

from tests.e2e.inertia_support import (  # noqa: F401
    inertia_context,
    inertia_storage_state,
    page,
    probes,
    reset_probes,
)

pytestmark = pytest.mark.e2e


def tick(page):
    return int(page.get_by_test_id("e2e-value-tick").inner_text())


def test_when_visible_loads_only_after_scroll(page, probes):
    page.goto("/__e2e/inertia/visible")
    expect(page.get_by_test_id("e2e-value-tick")).to_be_visible()
    first = tick(page)
    # let the 1s poll run at least once so "not loaded yet" is not just a race
    expect(page.get_by_test_id("e2e-value-tick")).not_to_have_text(str(first), timeout=4000)
    assert "below" not in probes()
    page.get_by_test_id("e2e-visible-spacer").scroll_into_view_if_needed()
    page.mouse.wheel(0, 10000)
    expect(page.get_by_test_id("e2e-value-below")).to_have_text("1")
    assert probes()["below"] == 1


def test_poll_updates_tick_repeatedly_and_stops(page):
    page.goto("/__e2e/inertia/visible")
    expect(page.get_by_test_id("e2e-value-tick")).to_have_text("1")
    expect(page.get_by_test_id("e2e-value-tick")).to_have_text("2", timeout=4000)
    expect(page.get_by_test_id("e2e-value-tick")).to_have_text("3", timeout=4000)
    page.get_by_test_id("e2e-poll-toggle").click()
    stopped = tick(page)
    page.wait_for_timeout(2500)  # must stay frozen for >2 poll intervals
    assert tick(page) == stopped
    page.get_by_test_id("e2e-poll-toggle").click()
    expect(page.get_by_test_id("e2e-value-tick")).not_to_have_text(str(stopped), timeout=4000)


def test_prefetch_on_hover_sends_purpose_header(page):
    page.goto("/__e2e/inertia/visible")
    link = page.get_by_test_id("e2e-prefetch-partial")
    with page.expect_request(lambda r: r.url.endswith("/__e2e/inertia/partial")) as info:
        link.hover()
    req = info.value
    assert req.headers.get("purpose") == "prefetch", req.headers
    assert req.headers.get("x-inertia") == "true"
    resp = req.response()
    assert resp is not None and resp.status == 200
    # clicking uses the prefetched response: no second request for /__e2e/inertia/partial
    more = []
    page.on(
        "request", lambda r: more.append(r) if r.url.endswith("/__e2e/inertia/partial") else None
    )
    link.click()
    expect(page.get_by_test_id("e2e-value-stamp")).to_be_visible()
    assert not more, [m.headers for m in more]
