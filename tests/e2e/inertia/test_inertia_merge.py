import json

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def val(page, name):
    return page.get_by_test_id(f"e2e-value-{name}")


def more(page, name, times=1):
    for _ in range(times):
        btn = page.get_by_test_id(f"e2e-more-{name}")
        expect(btn).to_be_enabled()
        btn.click()
        expect(btn).to_be_enabled()


def test_append_items(page):
    page.goto("/__e2e/inertia/merge")
    expect(val(page, "items")).to_have_text("[1,2,3]")
    more(page, "items")
    expect(val(page, "items")).to_have_text("[1,2,3,4,5,6]")
    more(page, "items")
    expect(val(page, "items")).to_have_text("[1,2,3,4,5,6,7,8,9]")


def test_prepend(page):
    page.goto("/__e2e/inertia/merge")
    expect(val(page, "prepended")).to_have_text("[-3,-2,-1]")
    more(page, "prepended")
    expect(val(page, "prepended")).to_have_text("[-6,-5,-4,-3,-2,-1]")


def test_deep_merge(page):
    page.goto("/__e2e/inertia/merge")
    more(page, "tree")
    expect(page.get_by_test_id("e2e-requests")).to_have_text("1")
    got = json.loads(val(page, "tree").inner_text())
    assert got == {"pages": {"1": 1, "2": 2}, "latest": 2}


def test_match_on_replaces_in_place(page):
    page.goto("/__e2e/inertia/merge")
    expect(val(page, "matched")).to_have_text('[{"id":1,"revision":1},{"id":2,"revision":1}]')
    more(page, "matched")
    got = json.loads(val(page, "matched").inner_text())
    assert got == [
        {"id": 1, "revision": 2},
        {"id": 2, "revision": 1},
        {"id": 3, "revision": 2},
    ]


def test_reset_replaces(page):
    page.goto("/__e2e/inertia/merge")
    more(page, "items", 2)
    expect(val(page, "items")).to_have_text("[1,2,3,4,5,6,7,8,9]")
    page.get_by_test_id("e2e-reset-items").click()
    expect(val(page, "items")).to_have_text("[1,2,3]")
    more(page, "items")
    expect(val(page, "items")).to_have_text("[1,2,3,4,5,6]")


def test_no_duplicates_after_many_loads(page):
    page.goto("/__e2e/inertia/merge")
    more(page, "items", 4)
    got = json.loads(val(page, "items").inner_text())
    assert got == list(range(1, 16))
