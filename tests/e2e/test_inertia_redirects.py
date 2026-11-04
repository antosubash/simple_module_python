import re

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


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_mutation_redirect_lands_with_done(page, method):
    page.goto("/__e2e/inertia/redirects")
    page.evaluate("window.__marker = 1")
    reqs = []
    page.on(
        "response",
        lambda r: (
            reqs.append((r.request.method, r.status, r.url))
            if "/__e2e/inertia/redirects" in r.url
            else None
        ),
    )
    page.get_by_test_id(f"e2e-redirect-{method}").click()
    expect(page).to_have_url(f"/__e2e/inertia/redirects?done={method}")
    expect(page.get_by_test_id("e2e-value-done")).to_have_text(f'"{method}"')
    assert page.evaluate("window.__marker") == 1, f"unexpected full reload; {reqs}"
    # a PUT/PATCH/DELETE must be followed by a GET, never replayed with the same verb
    assert reqs[0][0] == method.upper() and reqs[0][1] in (302, 303), reqs
    assert reqs[-1][0] == "GET", reqs


def test_empty_200_stays_on_page(page):
    page.goto("/__e2e/inertia/redirects")
    page.evaluate("window.__marker = 1")
    page.get_by_test_id("e2e-redirect-empty").click()
    expect(page.get_by_test_id("e2e-requests")).to_have_text("1")
    expect(page).to_have_url("/__e2e/inertia/redirects")
    expect(page.get_by_test_id("e2e-page")).to_be_visible()
    assert page.evaluate("window.__marker") == 1


def test_back_redirects_to_referer(page):
    page.goto("/__e2e/inertia/redirects?done=seed")
    page.get_by_test_id("e2e-redirect-back").click()
    expect(page.get_by_test_id("e2e-requests")).to_have_text("1")
    expect(page).to_have_url("/__e2e/inertia/redirects?done=seed")
    expect(page.get_by_test_id("e2e-value-done")).to_have_text('"seed"')


@pytest.mark.allow_resource_errors  # 409 + X-Inertia-Location is the protocol under test
def test_fragment_redirect_keeps_hash_and_scrolls(page):
    page.goto("/__e2e/inertia/redirects")
    assert page.evaluate("window.scrollY") == 0
    page.get_by_test_id("e2e-redirect-fragment").click()
    expect(page).to_have_url(re.compile(r"/__e2e/inertia/redirects#section-2$"))
    expect(page.get_by_test_id("e2e-section-2")).to_be_in_viewport()
    assert page.evaluate("window.scrollY") > 0


@pytest.mark.allow_resource_errors  # 409 + X-Inertia-Location is the protocol under test
def test_external_location_is_full_navigation(page):
    page.goto("/__e2e/inertia/redirects")
    page.evaluate("window.__marker = 1")
    page.get_by_test_id("e2e-redirect-external").click()
    expect(page.get_by_test_id("e2e-external")).to_be_visible()
    expect(page).to_have_url("/__e2e/inertia/_external")
    assert page.evaluate("window.__marker") is None
