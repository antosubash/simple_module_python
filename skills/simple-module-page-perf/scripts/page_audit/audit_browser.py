"""Browser side of the audit: what the user sees and feels.

An init script installed on every document records paint timings (FCP, LCP),
layout shifts (CLS, ignoring shifts the user caused) and every Inertia visit
through the public ``inertia:start`` / ``inertia:finish`` DOM events, so a
deferred-prop reload is told apart from the navigation that triggered it.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

SETTLE_TIMEOUT_MS = 15_000
_QUIET_MS = 300

INIT_SCRIPT = """
(() => {
  const s = (window.__pa = {
    cls: 0, shifts: 0, windowStart: 0, windowLast: 0, windowSum: 0,
    lcp: 0, fcp: 0, visits: [], pending: 0, last: 0,
  });
  const watch = (type, fn) => {
    try {
      new PerformanceObserver((l) => l.getEntries().forEach(fn)).observe({ type, buffered: true });
    } catch (e) { /* unsupported entry type */ }
  };
  watch('layout-shift', (e) => {
    if (e.hadRecentInput) return;
    if (s.shifts > 0 && e.startTime - s.windowLast < 1000
        && e.startTime - s.windowStart < 5000) {
      s.windowSum += e.value;
    } else {
      s.windowStart = e.startTime;
      s.windowSum = e.value;
    }
    s.windowLast = e.startTime;
    s.shifts += 1;
    s.cls = Math.max(s.cls, s.windowSum);
  });
  watch('largest-contentful-paint', (e) => { s.lcp = e.startTime; });
  watch('paint', (e) => { if (e.name === 'first-contentful-paint') s.fcp = e.startTime; });
  document.addEventListener('inertia:start', (ev) => {
    const visit = (ev.detail && ev.detail.visit) || {};
    s.pending += 1;
    s.visits.push({ start: performance.now(), partial: (visit.only || []).length > 0 });
  });
  document.addEventListener('inertia:finish', () => {
    s.pending = Math.max(0, s.pending - 1);
    s.last = performance.now();
    const v = s.visits.find((x) => x.finish === undefined);
    if (v) {
      v.finish = s.last;
      requestAnimationFrame(() => { v.painted = performance.now(); });
    }
  });
})();
"""

_SETTLED = f"""
() => window.__pa && window.__pa.pending === 0
  && window.__pa.visits.every((v) => v.painted !== undefined)
  && performance.now() - window.__pa.last > {_QUIET_MS}
"""

_RESET = """
() => {
  const s = window.__pa;
  s.cls = 0; s.shifts = 0; s.windowStart = 0; s.windowLast = 0; s.windowSum = 0;
  s.visits = [];
}
"""

_LOAD_METRICS = """
() => {
  const s = window.__pa;
  const nav = performance.getEntriesByType('navigation')[0] || {};
  const res = performance.getEntriesByType('resource');
  const size = (r) => r.transferSize || r.encodedBodySize || 0;
  const bytes = (pred) => res.filter(pred).reduce((t, r) => t + size(r), 0);
  const deferred = s.visits.filter((v) => v.partial && v.painted !== undefined);
  return {
    ttfb_ms: nav.responseStart || 0,
    dcl_ms: nav.domContentLoadedEventEnd || 0,
    fcp_ms: s.fcp, lcp_ms: s.lcp, cls: s.cls, shifts: s.shifts,
    deferred_done_ms: deferred.length ? Math.max(...deferred.map((v) => v.painted)) : null,
    html_bytes: nav.transferSize || nav.encodedBodySize || 0,
    js_bytes: bytes((r) => r.initiatorType === 'script' || /\\.(m?js|tsx?)(\\?|$)/.test(r.name)),
    css_bytes: bytes((r) => r.initiatorType === 'link' || /\\.css(\\?|$)/.test(r.name)),
    requests: res.length,
    dev_build: !!document.querySelector('script[src*="@vite/client"]'),
  };
}
"""

_NAV_METRICS = """
() => {
  const s = window.__pa;
  const main = s.visits.find((v) => !v.partial);
  if (!main) return null;
  const partial = s.visits.filter((v) => v.partial && v.painted !== undefined);
  return {
    nav_ms: main.painted - main.start,
    server_wait_ms: main.finish - main.start,
    deferred_done_ms: partial.length
      ? Math.max(...partial.map((v) => v.painted)) - main.start
      : null,
    cls: s.cls,
  };
}
"""

UX_CHECKS = """
() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const named = (el) => (el.innerText || '').trim() || el.getAttribute('aria-label')
    || el.getAttribute('aria-labelledby') || el.getAttribute('title')
    || (el.labels && el.labels.length > 0);
  const controls = [...document.querySelectorAll('button, a[href], [role="button"]')]
    .filter(visible);
  const loaders = [...document.querySelectorAll(
    '[aria-busy="true"], .animate-pulse, .animate-spin, [data-slot="skeleton"]')].filter(visible);
  const tbodies = [...document.querySelectorAll('tbody')];
  const root = document.documentElement;
  return {
    dom_nodes: document.getElementsByTagName('*').length,
    max_table_rows: tbodies.length ? Math.max(...tbodies.map((t) => t.rows.length)) : 0,
    unnamed_controls: controls.filter((el) => !named(el)).length,
    stuck_loaders: loaders.length,
    h1_count: document.querySelectorAll('h1').length,
    title: document.title,
    links: [...new Set([...document.querySelectorAll('main a[href^="/"]')]
      .filter(visible).map((a) => a.getAttribute('href')))],
    overflow_x: Math.max(0, root.scrollWidth - root.clientWidth),
  };
}
"""


@dataclass(slots=True)
class BrowserResult:
    path: str
    load: dict[str, Any] = field(default_factory=dict)
    nav: dict[str, Any] | None = None
    ux: dict[str, Any] = field(default_factory=dict)
    mobile_overflow_x: int | None = None
    console_errors: list[str] = field(default_factory=list)
    failed_requests: list[str] = field(default_factory=list)
    error: str = ""


def settle(page: Page) -> None:
    """Wait until no Inertia visit (including deferred reloads) is in flight."""
    with contextlib.suppress(PlaywrightError):
        page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
    page.wait_for_function(_SETTLED, timeout=SETTLE_TIMEOUT_MS)


def first_load(page: Page, url: str, result: BrowserResult) -> None:
    """A full document load of *url*: paint timings, bytes, shifts, UX checks."""
    page.goto(url, wait_until="load")
    settle(page)
    result.load = page.evaluate(_LOAD_METRICS)
    result.ux = page.evaluate(UX_CHECKS)


def client_navigation(
    page: Page, path: str, hubs: list[str], before_click: Callable[[], None]
) -> dict[str, Any] | None:
    """Click a visible link to *path* and time click -> painted -> deferred done.

    Tries the current page first, then loads each of *hubs* (a parent list
    page, the section index, the home page) until one links to *path*.
    Returns ``None`` when none does.
    """
    link = page.locator(f'a[href="{path}"]:visible').first
    for hub in hubs:
        if link.count():
            break
        page.goto(hub)
        settle(page)
        link = page.locator(f'a[href="{path}"]:visible').first
    if link.count() == 0:
        return None
    page.evaluate(_RESET)
    before_click()  # errors from here on belong to this page, not to the hubs
    link.click()
    page.wait_for_function(
        "() => window.__pa.visits.some((v) => !v.partial && v.painted !== undefined)",
        timeout=SETTLE_TIMEOUT_MS,
    )
    settle(page)
    return page.evaluate(_NAV_METRICS)


def mobile_overflow(page: Page, url: str) -> int:
    """Horizontal overflow in CSS pixels at a phone-sized viewport (0 is good)."""
    page.goto(url, wait_until="load")
    settle(page)
    return int(page.evaluate(UX_CHECKS)["overflow_x"])
