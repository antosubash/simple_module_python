"""Budgets, findings and the Markdown/JSON report.

Every budget is a ``(warn, fail)`` pair. The defaults follow the thresholds
users notice: ~100 ms feels instant, ~1 s keeps the flow of thought, and
Google's Core Web Vitals for LCP (2.5 s / 4 s) and CLS (0.1 / 0.25).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from audit_browser import BrowserResult
from audit_server import ServerResult

KB = 1024

BUDGETS: dict[str, tuple[float, float]] = {
    "app_ms": (100, 300),  # server time for an Inertia visit (warm)
    "queries": (12, 25),  # SQL statements per visit
    "page_kb": (100, 300),  # JSON without the i18n catalog
    "prop_kb": (50, 150),  # one prop
    "nav_ms": (300, 1000),  # click -> new page painted
    "deferred_ms": (1000, 2500),  # click -> every deferred prop painted
    "lcp_ms": (2500, 4000),  # first load
    "js_kb": (350, 600),  # JS transferred by a first load (production build)
    "cls": (0.1, 0.25),
    "dom_nodes": (1500, 3000),
    "table_rows": (100, 250),
}

HINTS = {
    "app_ms": "profile the handler; move slow work behind defer()/optional() or a cache",
    "queries": "likely N+1: eager-load (selectinload/joinedload) or batch the lookups",
    "page_kb": "paginate, send only the columns the page shows, defer() the heavy part",
    "prop_kb": "trim the DTO, paginate, or load it with defer()/WhenVisible",
    "nav_ms": "check server time first, then the page chunk size and render cost",
    "deferred_ms": "deferred groups load in parallel: split slow props into their own group",
    "lcp_ms": "largest element paints late: smaller first payload, defer below-the-fold data",
    "js_kb": "a heavy dependency on this page: lazy-load it (import()) where it is used",
    "cls": "reserve space for deferred/async content (fixed-height skeletons)",
    "dom_nodes": "paginate or virtualize long lists",
    "table_rows": "paginate (<=50 rows) or virtualize; use scroll() for infinite lists",
    "redirect": "link to the canonical URL; each redirect is an extra round trip",
    "console": "fix runtime errors/warnings; they often mean wasted renders",
    "failed_requests": "a request on this page failed",
    "overflow": "content wider than a phone screen: wrap tables in overflow-x-auto",
    "stuck_loaders": "a skeleton/spinner is still visible after every request settled",
    "unnamed_controls": "icon-only buttons/links need aria-label (screen readers, tooltips)",
    "h1": "give the page exactly one <h1> so its purpose is clear at a glance",
}


@dataclass(slots=True)
class Finding:
    path: str
    level: str  # "fail" | "warn"
    check: str
    detail: str

    @property
    def hint(self) -> str:
        return HINTS.get(self.check, "")


def _budget(path: str, check: str, value: float | None, label: str) -> list[Finding]:
    if value is None:
        return []
    warn, fail = BUDGETS[check]
    if value > fail:
        return [Finding(path, "fail", check, f"{label} {value:g} > {fail:g}")]
    if value > warn:
        return [Finding(path, "warn", check, f"{label} {value:g} > {warn:g}")]
    return []


def evaluate(server: ServerResult, browser: BrowserResult | None) -> list[Finding]:
    p = server.path
    if server.error:
        return [Finding(p, "fail", "server", server.error)]
    out: list[Finding] = []
    out += _budget(p, "app_ms", server.app_ms and round(server.app_ms), "server ms")
    out += _budget(p, "queries", server.queries, "SQL statements")
    page_kb = round((server.json_bytes - server.i18n_bytes) / KB, 1)
    out += _budget(p, "page_kb", page_kb, "page JSON KB")
    for name, size in server.top_props[:1]:
        out += _budget(p, "prop_kb", round(size / KB, 1), f"prop '{name}' KB")
    if server.redirected:
        out.append(Finding(p, "warn", "redirect", f"GET redirects to {server.final_url}"))
    if browser is None:
        return out
    if browser.error:
        return [*out, Finding(p, "fail", "browser", browser.error)]
    load, ux, nav = browser.load, browser.ux, browser.nav or {}
    if not load.get("dev_build"):  # dev-server timings and bytes are not what ships
        out += _budget(p, "lcp_ms", round(load.get("lcp_ms") or 0), "LCP ms")
        out += _budget(p, "js_kb", round((load.get("js_bytes") or 0) / KB), "JS KB")
    out += _budget(p, "cls", round(max(load.get("cls", 0), nav.get("cls", 0)), 3), "CLS")
    out += _budget(p, "nav_ms", nav.get("nav_ms") and round(nav["nav_ms"]), "navigation ms")
    # Click -> deferred painted when the page was reached by a link; otherwise
    # document start -> deferred painted from the full load, so a page with no
    # visible link is still held to the budget.
    if nav.get("deferred_done_ms") is not None:
        deferred, label = nav["deferred_done_ms"], "deferred ms"
    else:
        deferred, label = load.get("deferred_done_ms"), "deferred ms (first load)"
    out += _budget(p, "deferred_ms", deferred and round(deferred), label)
    out += _budget(p, "dom_nodes", ux.get("dom_nodes"), "DOM nodes")
    out += _budget(p, "table_rows", ux.get("max_table_rows"), "table rows")
    if browser.console_errors:
        out.append(Finding(p, "fail", "console", "; ".join(browser.console_errors[:3])[:300]))
    if browser.failed_requests:
        out.append(Finding(p, "fail", "failed_requests", ", ".join(browser.failed_requests[:3])))
    if browser.mobile_overflow_x:
        out.append(Finding(p, "warn", "overflow", f"{browser.mobile_overflow_x}px at 390px wide"))
    for check in ("stuck_loaders", "unnamed_controls"):
        if ux.get(check):
            out.append(Finding(p, "warn", check, f"{ux[check]} element(s)"))
    if ux.get("h1_count", 1) != 1:
        out.append(Finding(p, "warn", "h1", f"{ux.get('h1_count')} <h1> elements"))
    return out


def _fmt(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def markdown(rows: list[tuple[ServerResult, BrowserResult | None]], findings: list[Finding]) -> str:
    levels = {f.path: f.level for f in findings if f.level == "warn"}
    levels.update({f.path: f.level for f in findings if f.level == "fail"})
    lines = [
        "| Page | Component | Server ms | SQL | JSON KB | Deferred | Nav ms | LCP ms | CLS | DOM "
        "| Status |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for server, browser in rows:
        nav = (browser.nav if browser else None) or {}
        load = browser.load if browser else {}
        ux = browser.ux if browser else {}
        kb = (server.json_bytes - server.i18n_bytes) / KB
        lines.append(
            f"| `{server.path}` | {server.component or '—'} | {_fmt(server.app_ms)} "
            f"| {_fmt(server.queries)} | {kb:.1f} | {', '.join(server.deferred) or '—'} "
            f"| {_fmt(nav.get('nav_ms'))} | {_fmt(load.get('lcp_ms'))} "
            f"| {_fmt(max(load.get('cls', 0), nav.get('cls', 0)), 3)} | {ux.get('dom_nodes', '—')} "
            f"| {levels.get(server.path, 'ok')} |"
        )
    if findings:
        lines += ["", "## Findings", ""]
        for f in sorted(findings, key=lambda f: (f.level != "fail", f.path)):
            lines.append(f"- **{f.level}** `{f.path}` {f.check}: {f.detail} — {f.hint}")
    return "\n".join(lines)


def write_json(
    target: Path,
    rows: list[tuple[ServerResult, BrowserResult | None]],
    findings: list[Finding],
    meta: dict[str, Any],
) -> None:
    payload = {
        "meta": meta,
        "budgets": BUDGETS,
        "pages": [{"server": asdict(s), "browser": asdict(b) if b else None} for s, b in rows],
        "findings": [{**asdict(f), "hint": f.hint} for f in findings],
    }
    target.write_text(json.dumps(payload, indent=2, default=str))
