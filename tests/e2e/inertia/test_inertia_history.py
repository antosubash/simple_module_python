import json
import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

STATE = "JSON.stringify(window.history.state)"


def state(page):
    raw = page.evaluate(STATE)
    return json.loads(raw) if raw else None


def test_plain_page_history_state_is_readable(page):
    """Control: an unencrypted page exposes its component and props in history.state."""
    page.goto("/__e2e/inertia/partial")
    expect(page.get_by_test_id("e2e-value-stamp")).to_be_visible()
    page.wait_for_function("window.history.state && window.history.state.page")
    st = state(page)
    assert st["page"]["component"] == "E2eInertia/Partial", st


def test_encrypted_history_state(page):
    page.goto("/__e2e/inertia/")
    page.get_by_test_id("e2e-link-history").click()
    expect(page.get_by_test_id("e2e-value-history-mode")).to_have_text('"encrypt"')
    raw = page.evaluate(STATE)
    assert "E2eInertia/History" not in raw and "component" not in raw, raw[:300]
    st = json.loads(raw)
    assert isinstance(st["page"], (str, dict)) and not (
        isinstance(st["page"], dict) and "component" in st["page"]
    ), st
    assert page.evaluate("window.history.state.page === undefined") is False


def test_encrypted_page_survives_back_forward(page):
    page.goto("/__e2e/inertia/")
    page.evaluate("window.__marker = 1")
    page.get_by_test_id("e2e-link-history").click()
    expect(page.get_by_test_id("e2e-value-history-mode")).to_have_text('"encrypt"')
    page.go_back()
    expect(page.get_by_test_id("e2e-user-email")).to_be_visible()
    seen = []
    page.on("request", lambda r: seen.append(r.url))
    page.go_forward()
    expect(page.get_by_test_id("e2e-value-history-mode")).to_have_text('"encrypt"')
    assert page.evaluate("window.__marker") == 1, "decrypting should not need a reload"
    assert not [u for u in seen if "/__e2e/inertia/history" in u], (
        f"should restore from history: {seen}"
    )


def test_clear_history_forces_refetch_of_earlier_encrypted_entries(page, base_url):
    page.goto("/__e2e/inertia/history")
    expect(page.get_by_test_id("e2e-value-history-mode")).to_have_text('"encrypt"')
    page.evaluate("window.__marker = 1")
    page.get_by_test_id("e2e-history-clear").click()
    expect(page.get_by_test_id("e2e-value-history-mode")).to_have_text('"clear"')
    assert page.evaluate("window.__marker") == 1
    seen = []
    page.on(
        "request",
        lambda r: (
            seen.append((r.url, r.headers.get("x-inertia")))
            if "/__e2e/inertia/history" in r.url
            else None
        ),
    )
    page.go_back()
    # Key rotated: the previous encrypted entry cannot be decrypted, so the client
    # falls back to an Inertia XHR refetch (not a full document reload).
    expect(page.get_by_test_id("e2e-value-history-mode")).to_have_text('"encrypt"')
    expect(page).to_have_url("/__e2e/inertia/history")
    assert seen == [(f"{base_url}/__e2e/inertia/history", "true")], seen
    assert page.evaluate("window.__marker") == 1


def test_preserve_fragment_keeps_hash_across_a_redirect(page):
    page.goto("/__e2e/inertia/history")
    page.get_by_test_id("e2e-history-fragment").click()
    expect(page.get_by_test_id("e2e-value-history-mode")).to_have_text('"fragment"')
    expect(page).to_have_url(re.compile(r"/__e2e/inertia/history/fragment#history-section$"))
    expect(page.get_by_test_id("e2e-history-section")).to_be_in_viewport()


def test_redirect_without_preserve_fragment_drops_hash(page):
    """Control: proves the test above depends on the flag, not default client behaviour."""
    page.goto("/__e2e/inertia/history")
    page.get_by_test_id("e2e-history-fragment-plain").click()
    expect(page.get_by_test_id("e2e-value-history-mode")).to_have_text('"plain"')
    expect(page).to_have_url(re.compile(r"/__e2e/inertia/history/plain$"))
