"""Cold full-page-load benchmark, and a regression guard on compression.

Client-side navigation is ~32 ms and already fast. The cold full page load is
where the real cost sits: the whole JS/CSS bundle crosses the wire. Measured on
localhost that cost is invisible (infinite bandwidth), so these run under CDP
network throttling.

Drive via ``make bench-nav``; needs a running server and
``uv run playwright install chromium``.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Browser, Page, StorageState

from tests.perf.page_load_metrics import NetworkProfile, measure_cold_load

pytestmark = [pytest.mark.perf, pytest.mark.e2e]

ROUTES = ("/catalog/", "/dashboard/")
# Compression must cut total transfer by at least this much. The observed
# reduction is ~70%; 40% leaves generous headroom for bundle changes while
# still failing loudly if compression silently stops being applied.
MIN_COMPRESSION_SAVING = 0.40
# Cold load settled at 13-15 requests after chunk grouping, down from 55-63.
# The server speaks HTTP/1.1, so every request past the browser's ~6-connection
# limit adds a serial round trip; regressing here costs latency directly, not
# bytes. Generous headroom for new modules, tight enough to catch the chunk
# groups being dropped from vite.config.ts.
MAX_COLD_LOAD_REQUESTS = 30


@pytest.fixture
def storage_state(logged_in_page: Page) -> StorageState:
    """Auth state reusable across the fresh contexts each cold load needs."""
    return logged_in_page.context.storage_state()


def test_cold_page_load_under_throttled_network(
    browser: Browser, storage_state: StorageState, base_url: str, perf_build: str
) -> None:
    """Baseline cold-load timings on an ordinary broadband link."""
    profile = NetworkProfile()
    report = {
        route: measure_cold_load(browser, storage_state, f"{base_url}{route}", profile=profile)
        for route in ROUTES
    }
    print(f"\n=== cold page load ({perf_build}, {profile.label}) ===")
    print(json.dumps(report, indent=2))

    for route, metrics in report.items():
        assert metrics["fcp_ms"], f"{route}: no first-contentful-paint recorded"
        assert metrics["requests"] > 0, f"{route}: no resources recorded"
        assert metrics["requests"] <= MAX_COLD_LOAD_REQUESTS, (
            f"{route}: cold load makes {metrics['requests']} requests "
            f"(limit {MAX_COLD_LOAD_REQUESTS}). Over HTTP/1.1 each request past "
            "the ~6-connection limit is another serial round trip — are the "
            "advancedChunks groups still declared in vite.config.ts?"
        )


def test_compression_materially_reduces_cold_load(
    browser: Browser, storage_state: StorageState, base_url: str, perf_build: str
) -> None:
    """Compression must still be applied, and must still pay for itself.

    A/B'd by varying only the ``Accept-Encoding`` request header, so both arms
    hit the same running server. This is a regression guard: if GZipMiddleware
    is dropped or the static mount stops being covered, transfer size jumps
    back and this fails.
    """
    profile = NetworkProfile()
    url = f"{base_url}{ROUTES[0]}"

    compressed = measure_cold_load(
        browser, storage_state, url, profile=profile, accept_encoding="gzip, deflate, br"
    )
    plain = measure_cold_load(
        browser, storage_state, url, profile=profile, accept_encoding="identity"
    )

    saving = 1 - (compressed["transfer_kb"] / plain["transfer_kb"])
    print(f"\n=== compression A/B ({perf_build}, {profile.label}) ===")
    print(
        json.dumps(
            {
                "compressed": compressed,
                "identity": plain,
                "transfer_saving_pct": round(100 * saving, 1),
                "fcp_saving_pct": round(100 * (1 - compressed["fcp_ms"] / plain["fcp_ms"]), 1),
            },
            indent=2,
        )
    )

    assert saving >= MIN_COMPRESSION_SAVING, (
        f"compression saved only {saving:.1%} of transfer "
        f"({compressed['transfer_kb']}KB vs {plain['transfer_kb']}KB) — "
        "is GZipMiddleware still installed and covering /static?"
    )
