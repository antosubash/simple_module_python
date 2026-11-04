import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def ids(page):
    return (
        page.get_by_test_id("e2e-posts")
        .locator("li")
        .evaluate_all("els => els.map(e => Number(e.dataset.testid.split('-').pop()))")
    )


def scroll_until(page, last_id):
    for _ in range(60):
        if page.get_by_test_id(f"e2e-post-{last_id}").count():
            return
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(100)  # let the intersection observer fire; bounded loop
    raise AssertionError(f"post {last_id} never loaded; have {ids(page)}")


def test_scroll_loads_next_pages_without_duplicates(page):
    page.goto("/__e2e/inertia/scroll")
    expect(page.get_by_test_id("e2e-post-1")).to_be_visible()
    assert ids(page) == list(range(1, 11))
    scroll_until(page, 30)
    got = ids(page)
    assert len(got) == len(set(got)), f"duplicates: {got}"
    assert got[:30] == list(range(1, 31))
    assert got == sorted(got)


def test_url_page_param_updates(page):
    page.goto("/__e2e/inertia/scroll")
    scroll_until(page, 30)
    # Inertia's InfiniteScroll replaces the URL with the page of the most visible item.
    # The URL follows the most visible item, so keep scrolling (bounded) until it moves.
    for _ in range(40):
        if re.search(r"[?&]page=\d+", page.url):
            break
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(100)
    expect(page).to_have_url(re.compile(r"[?&]page=\d+"))


def test_reset_filter(page):
    page.goto("/__e2e/inertia/scroll")
    scroll_until(page, 20)
    page.get_by_test_id("e2e-reset-filter").click()
    expect(page.get_by_test_id("e2e-post-2")).to_be_visible()
    expect(page.get_by_test_id("e2e-post-1")).to_have_count(0)
    got = ids(page)
    assert got[:10] == list(range(2, 21, 2)), got
    assert len(got) == len(set(got))
    assert all(i % 2 == 0 for i in got)


def test_direct_page_param_load(page):
    page.goto("/__e2e/inertia/scroll?page=3")
    expect(page.get_by_test_id("e2e-post-21")).to_be_visible()
    assert ids(page)[0] == 21
