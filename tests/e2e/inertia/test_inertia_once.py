import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def val(page, name):
    return page.get_by_test_id(f"e2e-value-{name}")


def test_once_reused_after_navigating_away_and_back(page, probes):
    page.goto("/__e2e/inertia/")
    page.evaluate("window.__marker = 1")
    page.get_by_test_id("e2e-link-once").click()
    expect(val(page, "cached")).to_have_text("1")
    assert probes()["cached"] == 1
    page.get_by_test_id("e2e-once-away").click()
    expect(page.get_by_test_id("e2e-user-email")).to_be_visible()
    page.get_by_test_id("e2e-link-once").click()
    expect(val(page, "cached")).to_have_text("1")
    assert probes()["cached"] == 1, "cached once value must not be reloaded"
    assert page.evaluate("window.__marker") == 1


def test_once_expiry_refetches(page, probes):
    page.goto("/__e2e/inertia/once")
    expect(val(page, "expiring")).to_have_text("1")
    page.get_by_test_id("e2e-once-away").click()
    expect(page.get_by_test_id("e2e-user-email")).to_be_visible()
    page.get_by_test_id("e2e-link-once").click()
    expect(val(page, "expiring")).to_have_text("1")  # still fresh
    assert probes()["expiring"] == 1
    page.get_by_test_id("e2e-once-away").click()
    expect(page.get_by_test_id("e2e-user-email")).to_be_visible()
    page.wait_for_timeout(5500)  # real 5s server-side expiry; no event to wait on
    page.get_by_test_id("e2e-link-once").click()
    expect(val(page, "expiring")).to_have_text("2")
    assert probes()["expiring"] == 2
    assert probes()["cached"] == 1


def test_explicit_refresh_updates(page, probes):
    page.goto("/__e2e/inertia/once")
    expect(val(page, "cached")).to_have_text("1")
    page.get_by_test_id("e2e-refresh-once").click()
    expect(val(page, "cached")).to_have_text("2")
    assert probes()["cached"] == 2
    page.get_by_test_id("e2e-refresh-expiring").click()
    expect(val(page, "expiring")).to_have_text("2")
