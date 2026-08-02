"""Instrumentation for Inertia client-side navigations.

Hooks the global ``inertia:start`` / ``inertia:finish`` DOM events that Inertia
dispatches on ``document``. That is a public part of Inertia's API, so the app
needs no test-only hook and the production bundle stays untouched.

``start`` fires when the request leaves, ``finish`` when the response has been
applied to the page; a ``requestAnimationFrame`` after ``finish`` approximates
the paint that follows. Response size and TTFB come from Playwright's network
layer, which the DOM events don't expose.

Note this measures *client-side* navigation — clicking a link within an
already-loaded SPA. A full ``page.goto()`` document load does not fire these
events, and is a different (much heavier) code path.
"""

from __future__ import annotations

import contextlib
import statistics
from collections.abc import Callable
from dataclasses import dataclass

from playwright.sync_api import Page, Response

PERCENTILE_95 = 0.95
_NAV_TIMEOUT_MS = 30_000

_INSTALL_HOOK = """
() => {
  window.__navMetrics = { pending: null, samples: [] };
  document.addEventListener('inertia:start', () => {
    window.__navMetrics.pending = { start: performance.now() };
  });
  document.addEventListener('inertia:finish', () => {
    const p = window.__navMetrics.pending;
    if (!p) return;
    p.finish = performance.now();
    requestAnimationFrame(() => {
      p.painted = performance.now();
      window.__navMetrics.samples.push(p);
      window.__navMetrics.pending = null;
    });
  });
}
"""

_SAMPLE_COUNT = "() => window.__navMetrics ? window.__navMetrics.samples.length : 0"
_READ_LAST = """
() => {
  const s = window.__navMetrics.samples;
  return s.length ? s[s.length - 1] : null;
}
"""


@dataclass(frozen=True, slots=True)
class NavSample:
    """One measured Inertia client-side navigation.

    The phases partition ``total_ms``::

        start ──────────────── finish ──────── painted
              └── request_ms ──┘└── render_ms ─┘
              └── ttfb_ms ─┘

    ``ttfb_ms`` is the server's share and sits *inside* ``request_ms``; the
    remainder of ``request_ms`` is client-side — response transfer, JSON parse,
    the dynamic import of the page component chunk, and React reconciliation.
    That remainder is where an unexplained navigation cost shows up.
    """

    route: str
    ttfb_ms: float
    response_bytes: int
    request_ms: float
    render_ms: float
    total_ms: float

    @property
    def client_request_ms(self) -> float:
        """``request_ms`` minus the server's contribution."""
        return max(0.0, self.request_ms - self.ttfb_ms)


def install_hooks(page: Page) -> None:
    """Install navigation timing hooks on the current page.

    Must be re-run after any full document load, since the listeners live on
    the document being replaced.
    """
    page.evaluate(_INSTALL_HOOK)


def measure_navigation(page: Page, trigger: Callable[[], None], route: str) -> NavSample:
    """Run *trigger* (typically a click) and return that navigation's timings."""
    sizes: list[int] = []
    ttfbs: list[float] = []

    def _on_response(response: Response) -> None:
        if response.request.resource_type not in ("xhr", "fetch"):
            return
        # Body already discarded (redirect, aborted request) — the timing below
        # is still usable, so don't fail the whole sample over a missing size.
        with contextlib.suppress(Exception):
            sizes.append(len(response.body()))
        timing = response.request.timing
        ttfbs.append(timing["responseStart"] - timing["requestStart"])

    before = page.evaluate(_SAMPLE_COUNT)
    page.on("response", _on_response)
    try:
        trigger()
        page.wait_for_function(
            f"() => window.__navMetrics"
            f" && window.__navMetrics.pending === null"
            f" && window.__navMetrics.samples.length > {before}",
            timeout=_NAV_TIMEOUT_MS,
        )
        raw = page.evaluate(_READ_LAST)
    finally:
        page.remove_listener("response", _on_response)

    return NavSample(
        route=route,
        ttfb_ms=max(ttfbs) if ttfbs else 0.0,
        response_bytes=max(sizes) if sizes else 0,
        request_ms=raw["finish"] - raw["start"],
        render_ms=raw["painted"] - raw["finish"],
        total_ms=raw["painted"] - raw["start"],
    )


def summarize(samples: list[NavSample]) -> dict[str, float]:
    """Median and p95 across a sample set.

    Median rather than mean — a single GC pause or a background tab throttle
    shouldn't move the headline number.
    """
    if not samples:
        raise ValueError("no samples to summarize")
    totals = sorted(s.total_ms for s in samples)
    p95_index = min(int(len(totals) * PERCENTILE_95), len(totals) - 1)
    return {
        "n": len(samples),
        "median_total_ms": round(statistics.median(totals), 2),
        "p95_total_ms": round(totals[p95_index], 2),
        # Phase breakdown — server, client-side request handling, then paint.
        "median_ttfb_ms": round(statistics.median([s.ttfb_ms for s in samples]), 2),
        "median_client_request_ms": round(
            statistics.median([s.client_request_ms for s in samples]), 2
        ),
        "median_render_ms": round(statistics.median([s.render_ms for s in samples]), 2),
        "median_bytes": int(statistics.median([s.response_bytes for s in samples])),
    }
