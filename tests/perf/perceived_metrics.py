"""Perceived-smoothness instrumentation: layout shift.

Everything else in this package measures *duration*. A page can hit a fast
First Contentful Paint and still feel bad if content reflows after paint —
the user loses their place and has to re-find what they were reading. That is
Cumulative Layout Shift, and no timing metric captures it.

Only shifts with ``hadRecentInput === false`` count: one the user caused by
clicking is expected, not a defect.

**Long tasks are deliberately not measured here.** The `longtask` observer
arms without error in Playwright's Chromium but never receives entries — a
forced 250 ms blocking loop goes unrecorded in both `chromium-headless-shell`
and `channel=chromium`. It would therefore report a permanent, false zero,
which is worse than reporting nothing. If you need long-task data, measure it
in a real browser session rather than trusting this harness.
"""

from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import Page

# Google's Core Web Vitals thresholds for CLS.
CLS_GOOD = 0.1
CLS_POOR = 0.25

_INSTALL = """
() => {
  window.__perceived = { shifts: [] };
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      // A shift the user just caused by interacting is expected, not a defect.
      if (!entry.hadRecentInput) {
        window.__perceived.shifts.push({ value: entry.value, time: entry.startTime });
      }
    }
  }).observe({ type: 'layout-shift', buffered: true });
}
"""

_READ = """
() => {
  const p = window.__perceived || { shifts: [] };
  const cls = p.shifts.reduce((t, s) => t + s.value, 0);
  return {
    cls: Math.round(cls * 10000) / 10000,
    shift_count: p.shifts.length,
    largest_shift: p.shifts.length ? Math.max(...p.shifts.map(s => s.value)) : 0,
  };
}
"""

_RESET = "() => { window.__perceived = { shifts: [] }; }"

# Grows an element so everything below it moves — an unmistakable shift, used
# to prove the observer is live before a zero reading is believed.
FORCE_SHIFT = """
() => {
  const d = document.createElement('div');
  d.style.height = '500px';
  d.setAttribute('data-forced-shift', '');
  document.body.insertBefore(d, document.body.firstChild);
}
"""


@dataclass(frozen=True, slots=True)
class PerceivedSample:
    """Layout-shift totals for one measured window."""

    label: str
    cls: float
    shift_count: int
    largest_shift: float

    @property
    def rating(self) -> str:
        """Google's Core Web Vitals bucket for this CLS value."""
        if self.cls <= CLS_GOOD:
            return "good"
        return "needs-improvement" if self.cls <= CLS_POOR else "poor"

    def as_dict(self) -> dict:
        return {
            "cls": self.cls,
            "cls_rating": self.rating,
            "shift_count": self.shift_count,
            "largest_shift": round(self.largest_shift, 4),
        }


def arm_perceived_observers(page: Page) -> None:
    """Arm the observer for every *subsequent* navigation on this page.

    Registered via ``add_init_script`` so it runs before any page script and
    catches shifts that happen during load, not just after it.
    """
    page.add_init_script(f"({_INSTALL})()")


def install_perceived_observers(page: Page) -> None:
    """Start observing on the *current* document.

    For measuring what happens next (e.g. a client-side navigation). For
    load-time metrics use :func:`arm_perceived_observers`.
    """
    page.evaluate(_INSTALL)


def reset_perceived(page: Page) -> None:
    """Clear accumulated entries so the next window is measured in isolation."""
    page.evaluate(_RESET)


def read_perceived(page: Page, label: str) -> PerceivedSample:
    raw = page.evaluate(_READ)
    return PerceivedSample(
        label=label,
        cls=raw["cls"],
        shift_count=raw["shift_count"],
        largest_shift=raw["largest_shift"],
    )


def force_layout_shift(page: Page) -> None:
    """Cause a large, unmistakable layout shift on the current page."""
    page.evaluate(FORCE_SHIFT)
