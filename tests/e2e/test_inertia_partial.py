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


def v(page, name):
    return page.get_by_test_id(f"e2e-value-{name}")


def test_initial_state_optional_missing(page, probes):
    page.goto("/__e2e/inertia/partial")
    expect(v(page, "stamp")).to_have_text("1")
    expect(v(page, "b")).to_have_text("1")
    expect(v(page, "nested-x")).to_have_text("1")
    expect(v(page, "nested-y")).to_have_text("1")
    p = probes()
    assert "a" not in p
    assert p["stamp"] == 1 and p["b"] == 1


def test_only_a(page, probes):
    page.goto("/__e2e/inertia/partial")
    expect(v(page, "stamp")).to_have_text("1")
    page.get_by_test_id("e2e-only-a").click()
    expect(v(page, "a")).to_have_text("1")
    expect(v(page, "stamp")).to_have_text("2")  # always props ride along
    expect(v(page, "b")).to_have_text("1")  # untouched
    expect(v(page, "nested-x")).to_have_text("1")
    p = probes()
    assert p["a"] == 1 and p["b"] == 1 and p["stamp"] == 2
    assert p["nested.x"] == 1 and p["nested.y"] == 1


def test_except_b(page, probes):
    page.goto("/__e2e/inertia/partial")
    expect(v(page, "stamp")).to_have_text("1")
    page.get_by_test_id("e2e-except-b").click()
    expect(v(page, "stamp")).to_have_text("2")
    expect(v(page, "nested-x")).to_have_text("2")
    expect(v(page, "nested-y")).to_have_text("2")
    expect(v(page, "b")).to_have_text("1")
    p = probes()
    assert p["b"] == 1, "excluded loader must not run"
    # Observed: with `except` only (no `only`), the server evaluates optional prop `a`
    # (Inertia's reference adapters do the same: optional is only skipped on non-partial
    # requests). Pinned so a change in behaviour is noticed.
    assert p.get("a") == 1
    assert p["nested.x"] == 2


def test_only_dotted_nested_x(page, probes):
    page.goto("/__e2e/inertia/partial")
    expect(v(page, "stamp")).to_have_text("1")
    page.get_by_test_id("e2e-only-nested-x").click()
    expect(v(page, "nested-x")).to_have_text("2")
    expect(v(page, "stamp")).to_have_text("2")
    p = probes()
    assert p["nested.x"] == 2
    assert p["nested.y"] == 1, "dotted only must not run sibling loader"
    assert p["b"] == 1
    # Sibling value must survive in the client (nested object merged, not replaced).
    expect(v(page, "nested-y")).to_have_text("1")
