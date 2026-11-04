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


def err(page, bag, field):
    return page.get_by_test_id(f"e2e-{bag}-{field}-error")


def test_default_bag_errors_only_in_default_form(page):
    page.goto("/__e2e/inertia/forms")
    page.get_by_test_id("e2e-default-submit").click()
    expect(err(page, "default", "name")).not_to_be_empty()
    expect(err(page, "default", "email")).not_to_be_empty()
    expect(err(page, "second", "name")).to_be_empty()
    expect(err(page, "second", "email")).to_be_empty()


def test_second_bag_errors_only_in_second_form(page):
    page.goto("/__e2e/inertia/forms")
    page.get_by_test_id("e2e-second-submit").click()
    expect(err(page, "second", "name")).not_to_be_empty()
    expect(err(page, "second", "email")).not_to_be_empty()
    expect(err(page, "default", "name")).to_be_empty()
    expect(err(page, "default", "email")).to_be_empty()


def test_bags_independent_then_success_clears(page):
    page.goto("/__e2e/inertia/forms")
    page.get_by_test_id("e2e-default-submit").click()
    expect(err(page, "default", "name")).not_to_be_empty()
    page.get_by_test_id("e2e-second-submit").click()
    expect(err(page, "second", "name")).not_to_be_empty()
    # the second submission must not have wiped/leaked the default bag's errors
    expect(err(page, "default", "name")).not_to_be_empty()
    page.get_by_test_id("e2e-default-name").fill("Ada")
    page.get_by_test_id("e2e-default-email").fill("ada@example.com")
    page.get_by_test_id("e2e-default-submit").click()
    expect(page.get_by_test_id("e2e-form-success")).to_contain_text("default")
    for field in ("name", "email"):
        expect(err(page, "default", field)).to_be_empty()
    expect(page).to_have_url("/__e2e/inertia/forms?success=default")


def test_partial_invalid_shows_only_bad_field(page):
    page.goto("/__e2e/inertia/forms")
    page.get_by_test_id("e2e-second-name").fill("Ada")
    page.get_by_test_id("e2e-second-email").fill("nope")
    page.get_by_test_id("e2e-second-submit").click()
    expect(err(page, "second", "email")).not_to_be_empty()
    expect(err(page, "second", "name")).to_be_empty()
    expect(err(page, "default", "email")).to_be_empty()


@pytest.mark.allow_resource_errors
@pytest.mark.xfail(strict=False, reason="fixed by #818")
def test_validated_route_returns_field_errors(page):
    page.goto("/__e2e/inertia/forms")
    seen = []
    page.on(
        "response",
        lambda r: (
            seen.append((r.status, r.url, r.headers.get("content-type")))
            if "/__e2e/inertia/forms/validated" in r.url
            else None
        ),
    )
    page.get_by_test_id("e2e-validated-submit").click()
    expect(err(page, "default", "name")).not_to_be_empty(timeout=3000)
    expect(page).to_have_url("/__e2e/inertia/forms")
