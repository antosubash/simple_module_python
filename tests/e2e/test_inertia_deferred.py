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


def test_fallback_then_resolve_and_groups(page, probes):
    page.goto("/__e2e/inertia/deferred")
    # slow group takes 300ms server side, so its fallback is observable
    expect(page.get_by_test_id("e2e-slow-loading")).to_be_visible()
    expect(page.get_by_test_id("e2e-value-fast")).to_have_text("1")
    expect(page.get_by_test_id("e2e-value-slow")).to_have_text("1")
    expect(page.get_by_test_id("e2e-slow-loading")).to_have_count(0)
    expect(page.get_by_test_id("e2e-fast-loading")).to_have_count(0)
    p = probes()
    assert p["fast"] == 1 and p["slow"] == 1


def test_groups_load_in_separate_requests(page):
    reqs = []
    page.on(
        "request",
        lambda r: (
            reqs.append(r.headers.get("x-inertia-partial-data"))
            if r.headers.get("x-inertia-partial-data")
            else None
        ),
    )
    page.goto("/__e2e/inertia/deferred")
    expect(page.get_by_test_id("e2e-value-slow")).to_have_text("1")
    expect(page.get_by_test_id("e2e-fragile-failed")).to_be_visible()
    flat = ",".join(r for r in reqs)
    assert "slow" in flat and "fast" in flat
    assert not any("slow" in r and "fast" in r for r in reqs), f"groups merged: {reqs}"


def test_rescued_prop_shows_failure(page, probes):
    page.goto("/__e2e/inertia/deferred")
    expect(page.get_by_test_id("e2e-fragile-failed")).to_be_visible()
    expect(page.get_by_test_id("e2e-fragile-ready")).to_have_count(0)
    # the rest of the page still works
    expect(page.get_by_test_id("e2e-value-fast")).to_have_text("1")
    assert probes()["fragile"] == 1
