"""Full page-load measurement under emulated network conditions.

Client-side navigation (see ``nav_metrics``) is only half the story: a cold
full page load pays for the whole JS/CSS bundle, and that cost is invisible on
localhost where bandwidth is effectively infinite. Throttling via CDP is what
makes transfer size show up as time.
"""

from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import Browser, BrowserContext, Page, StorageState

# A deliberately ordinary connection — fast enough not to be a strawman, slow
# enough that payload size actually costs time. Roughly a weak broadband link.
DEFAULT_MBPS = 4
DEFAULT_LATENCY_MS = 40
_BITS_PER_BYTE = 8
_BYTES_PER_MBIT = 1024 * 1024 / _BITS_PER_BYTE
_SETTLE_MS = 2500
_LOAD_TIMEOUT_MS = 120_000

_METRICS = """
() => {
  const nav = performance.getEntriesByType('navigation')[0];
  const paints = Object.fromEntries(
    performance.getEntriesByType('paint').map(p => [p.name, Math.round(p.startTime)])
  );
  const res = performance.getEntriesByType('resource');
  const sum = a => a.reduce((t, r) => t + (r.transferSize || 0), 0);
  const js = res.filter(r => r.name.endsWith('.js'));
  const css = res.filter(r => r.name.endsWith('.css'));
  return {
    fcp_ms: paints['first-contentful-paint'] ?? null,
    load_ms: Math.round(nav.loadEventEnd),
    transfer_kb: Math.round((sum(res) + (nav.transferSize || 0)) / 1024),
    js_transfer_kb: Math.round(sum(js) / 1024),
    css_transfer_kb: Math.round(sum(css) / 1024),
    requests: res.length,
  };
}
"""


@dataclass(frozen=True, slots=True)
class NetworkProfile:
    """Emulated link characteristics for a cold-load measurement."""

    mbps: float = DEFAULT_MBPS
    latency_ms: int = DEFAULT_LATENCY_MS

    @property
    def label(self) -> str:
        return f"{self.mbps}Mbps/{self.latency_ms}ms"


def measure_cold_load(
    browser: Browser,
    storage_state: StorageState,
    url: str,
    *,
    profile: NetworkProfile | None = None,
    accept_encoding: str | None = None,
    viewport: dict | None = None,
) -> dict[str, float]:
    """Load *url* in a brand-new context (empty HTTP cache) and report timings.

    A fresh context is what makes the load "cold" — reusing a page would hit
    the memory/disk cache and measure nothing. ``accept_encoding`` overrides
    the request header, which is how compression is A/B'd without restarting
    the server.
    """
    profile = profile or NetworkProfile()
    context: BrowserContext = browser.new_context(
        viewport=viewport or {"width": 1440, "height": 900},
        storage_state=storage_state,
    )
    try:
        page: Page = context.new_page()
        if accept_encoding is not None:
            page.set_extra_http_headers({"Accept-Encoding": accept_encoding})
        cdp = context.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send(
            "Network.emulateNetworkConditions",
            {
                "offline": False,
                "downloadThroughput": profile.mbps * _BYTES_PER_MBIT,
                "uploadThroughput": profile.mbps * _BYTES_PER_MBIT,
                "latency": profile.latency_ms,
            },
        )
        page.goto(url, wait_until="load", timeout=_LOAD_TIMEOUT_MS)
        page.wait_for_timeout(_SETTLE_MS)
        return page.evaluate(_METRICS)
    finally:
        context.close()
