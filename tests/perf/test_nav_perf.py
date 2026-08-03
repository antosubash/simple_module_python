"""Navigation performance benchmark.

Measures click -> painted for Inertia client-side navigations, plus the
per-navigation payload size. This is the metric the "page navigation feels
slow" complaint is actually about — no other test in the repo covers it.

Navigations are driven by clicking real links, not ``page.goto()``: a goto is
a full document load, which is a different and much heavier code path than the
client-side navigation a user experiences when clicking around the app.

Prerequisites: a running server against the seeded database, and
``uv run playwright install chromium``. Drive it via ``make bench-nav``.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page

from tests.perf.nav_metrics import NavSample, install_hooks, measure_navigation, summarize

pytestmark = [pytest.mark.perf, pytest.mark.e2e]

# (label, href) — href must match the sidebar link's href exactly, and that
# href must be the canonical path. Linking to a redirecting path would add a
# round trip to every sample; framework/hosting/tests/test_menu_urls_are_canonical.py
# enforces that no menu URL redirects.
ROUTES = (
    ("dashboard", "/dashboard/"),
    ("users_admin", "/users/admin"),
    ("audit_log", "/audit_log/"),
)


def _click_sidebar(page: Page, href: str) -> None:
    """Click the sidebar link for *href*.

    ``:visible`` is required — the layout also renders a collapsed-state brand
    link pointing at /dashboard/, which is hidden at desktop widths. Matching
    it would hang the click waiting for an element that never becomes visible.
    """
    page.locator(f'a[href="{href}"]:visible').first.click()


def _report(title: str, build: str, data: dict[str, dict[str, float]]) -> None:
    print(f"\n=== {title} ({build}) ===")
    print(json.dumps(data, indent=2))


def test_sidebar_navigation_timings(
    logged_in_page: Page, perf_rounds: int, perf_build: str
) -> None:
    """Round-robin the sidebar routes, recording every client-side navigation."""
    page = logged_in_page
    install_hooks(page)

    samples: dict[str, list[NavSample]] = {name: [] for name, _ in ROUTES}
    for _ in range(perf_rounds):
        for name, href in ROUTES:
            samples[name].append(
                measure_navigation(page, lambda h=href: _click_sidebar(page, h), name)
            )

    _report("sidebar navigation", perf_build, {k: summarize(v) for k, v in samples.items()})

    # No hard threshold — this is a measurement, not a gate. Assert only that
    # every route produced usable samples, so a silently broken selector fails
    # loudly instead of reporting a suspiciously fast, empty run.
    for name, rows in samples.items():
        assert len(rows) == perf_rounds, f"{name}: expected {perf_rounds} samples, got {len(rows)}"
        assert all(s.total_ms > 0 for s in rows), f"{name}: zero-duration sample"


def test_shared_props_payload_share(logged_in_page: Page, perf_build: str) -> None:
    """How much of a navigation's payload is static shared props?

    This is the measurement that decides whether suspect S3 (menus and
    permissions re-sent on every navigation) is worth fixing. Reported, not
    asserted — the number is the point.
    """
    page = logged_in_page
    install_hooks(page)

    captured: dict[str, int] = {}

    def _on_response(response) -> None:
        if response.request.resource_type not in ("xhr", "fetch"):
            return
        try:
            body = response.json()
        except Exception:
            return
        props = body.get("props") if isinstance(body, dict) else None
        if not isinstance(props, dict):
            return
        total = len(json.dumps(body))
        menus = len(json.dumps(props.get("menus"))) if "menus" in props else 0
        auth = props.get("auth") or {}
        perms = len(json.dumps(auth.get("permissions"))) if "permissions" in auth else 0
        i18n = props.get("i18n") or {}
        messages = len(json.dumps(i18n.get("messages"))) if i18n.get("messages") else 0
        captured.update(
            total_bytes=total,
            menus_bytes=menus,
            permissions_bytes=perms,
            i18n_messages_bytes=messages,
            static_share_pct=round(100 * (menus + perms) / total, 1) if total else 0,
        )

    page.on("response", _on_response)
    try:
        measure_navigation(page, lambda: _click_sidebar(page, "/audit_log/"), "audit_log")
    finally:
        page.remove_listener("response", _on_response)

    _report("shared-props payload share", perf_build, {"audit_log": captured})
    assert captured, "no Inertia JSON response captured"
