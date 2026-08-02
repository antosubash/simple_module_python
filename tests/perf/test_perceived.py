"""Perceived-smoothness benchmark: layout stability.

Every other measurement in this package is a duration. This one asks whether
the page *feels* stable — content that reflows after paint makes the user
re-find what they were reading, and no timing metric captures it.

The first test proves the instrument is live. Without it a broken observer
would report a perfect CLS of 0 forever and nobody would notice; that is
exactly what happened while this file was being written.

Prerequisites: a running server and ``uv run playwright install chromium``.
Drive via ``make bench-nav``.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page

from tests.perf.nav_metrics import install_hooks, measure_navigation
from tests.perf.perceived_metrics import (
    CLS_POOR,
    arm_perceived_observers,
    force_layout_shift,
    install_perceived_observers,
    read_perceived,
    reset_perceived,
)

pytestmark = [pytest.mark.perf, pytest.mark.e2e]

ROUTES = (
    ("dashboard", "/dashboard/"),
    ("catalog_list", "/catalog/"),
    ("users_admin", "/users/admin"),
    ("audit_log", "/audit_log/"),
)
_SETTLE_MS = 1200
# A 500px block inserted at the top of the body shifts essentially the whole
# viewport; anything near zero here means the observer is not recording.
_MIN_DETECTED_FORCED_SHIFT = 0.1


def _click_sidebar(page: Page, href: str) -> None:
    page.locator(f'a[href="{href}"]:visible').first.click()


def test_layout_shift_observer_is_live(page: Page, base_url: str) -> None:
    """Prove the instrument works before believing any zero it reports.

    A PerformanceObserver that arms without error but never fires reports a
    permanent, false 'perfect'. This forces a shift the observer must catch.
    """
    arm_perceived_observers(page)
    page.goto(f"{base_url}/users/login", wait_until="load")
    page.wait_for_timeout(_SETTLE_MS)

    force_layout_shift(page)
    page.wait_for_timeout(_SETTLE_MS)
    sample = read_perceived(page, "forced")

    assert sample.shift_count > 0, (
        "layout-shift observer recorded nothing after a forced 500px reflow — "
        "the CLS numbers from the other tests in this file cannot be trusted"
    )
    assert sample.cls >= _MIN_DETECTED_FORCED_SHIFT, (
        f"forced reflow registered only {sample.cls}; observer may be partially working"
    )


def test_cold_load_layout_stability(page: Page, base_url: str, perf_build: str) -> None:
    """Layout shift across a full page load, per route."""
    arm_perceived_observers(page)
    report = {}
    for name, route in ROUTES:
        page.goto(f"{base_url}{route}", wait_until="load")
        page.wait_for_timeout(_SETTLE_MS)
        report[name] = read_perceived(page, name).as_dict()

    print(f"\n=== cold load: layout stability ({perf_build}) ===")
    print(json.dumps(report, indent=2))

    for name, metrics in report.items():
        assert metrics["cls"] <= CLS_POOR, (
            f"{name}: CLS {metrics['cls']} is in Google's 'poor' band "
            f"(> {CLS_POOR}) — content visibly reflows after paint across "
            f"{metrics['shift_count']} shifts"
        )


def test_client_navigation_layout_stability(logged_in_page: Page, perf_build: str) -> None:
    """Layout shift caused by an Inertia navigation specifically.

    The accumulator is reset between routes so each route's shifts are
    attributed to that route rather than to the whole session.
    """
    page = logged_in_page
    install_hooks(page)
    # add_init_script only applies to future documents, so install on the
    # current one too — this page was already loaded by the login fixture.
    arm_perceived_observers(page)
    install_perceived_observers(page)

    report = {}
    for name, href in ROUTES:
        reset_perceived(page)
        measure_navigation(page, lambda h=href: _click_sidebar(page, h), name)
        page.wait_for_timeout(_SETTLE_MS)
        report[name] = read_perceived(page, name).as_dict()

    print(f"\n=== client navigation: layout stability ({perf_build}) ===")
    print(json.dumps(report, indent=2))

    for name, metrics in report.items():
        assert metrics["cls"] <= CLS_POOR, (
            f"{name}: navigating here shifts layout by {metrics['cls']} "
            f"(> {CLS_POOR}) across {metrics['shift_count']} shifts"
        )
