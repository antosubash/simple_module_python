"""Audit every Inertia page of a running simple_module app for speed and UX.

    uv run --with playwright python <skill>/scripts/page_audit \\
        --base-url http://localhost:8000 --email admin@example.com --password '...'

Signs in, discovers pages from the ``menus`` shared prop (plus any ``--path``),
then for each page measures the Inertia JSON response (server time and SQL
statements from the development ``Server-Timing`` header, payload size, the
largest props, deferred props), a full document load (FCP, LCP, CLS, bytes), a
client-side navigation by clicking a link (click -> painted -> deferred
props painted) and UX checks (DOM size, table rows, stuck loaders, unnamed
icon buttons, headings, horizontal overflow on a phone). Prints a Markdown
report, optionally writes JSON, and exits 1 when any check fails.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

from audit_browser import (
    INIT_SCRIPT,
    BrowserResult,
    client_navigation,
    first_load,
    mobile_overflow,
    settle,
)
from audit_crawl import extra_pages, hubs_for
from audit_report import BUDGETS, Finding, evaluate, markdown, write_json
from audit_server import discover_paths, inertia_headers, probe
from playwright.sync_api import BrowserContext, Page, ViewportSize, sync_playwright

DESKTOP: ViewportSize = {"width": 1440, "height": 900}
PHONE: ViewportSize = {"width": 390, "height": 844}
DEFAULT_EXCLUDE = (
    r"logout|log-out|sign-?out|switch|impersonat|delete|remove|revoke|"
    r"/api/|/static/|/setup|download|export|\.(csv|json|pdf|zip)$"
)
_PAGE_OBJECT = """
() => {
  const el = document.querySelector('script[data-page]');
  if (el) return JSON.parse(el.textContent);
  const app = document.getElementById('app');
  return app && app.dataset.page ? JSON.parse(app.dataset.page) : null;
}
"""


def _args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="page_audit", description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--base-url", default=os.environ.get("PAGE_AUDIT_BASE_URL", "http://localhost:8000")
    )
    ap.add_argument("--email", default=os.environ.get("PAGE_AUDIT_EMAIL"))
    ap.add_argument("--password", default=os.environ.get("PAGE_AUDIT_PASSWORD"))
    ap.add_argument("--login-path", default="/users/login")
    ap.add_argument("--storage-state", help="Playwright storage state of a signed-in session")
    ap.add_argument("--path", action="append", default=[], help="page to audit (repeatable)")
    ap.add_argument("--no-discover", action="store_true", help="only audit --path pages")
    ap.add_argument("--crawl-depth", type=int, default=2, help="link levels to follow (0: none)")
    ap.add_argument("--max-pages", type=int, default=80, help="cap including crawled pages")
    ap.add_argument("--exclude", action="append", default=[DEFAULT_EXCLUDE], help="regex to skip")
    ap.add_argument("--rounds", type=int, default=5, help="warm server samples per page")
    ap.add_argument("--server-only", action="store_true", help="skip the browser checks")
    ap.add_argument("--no-mobile", action="store_true", help="skip the phone-width pass")
    ap.add_argument("--budget", action="append", default=[], help="override: queries=20,40")
    ap.add_argument("--json", type=Path, help="also write the full results here")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--no-fail", action="store_true", help="exit 0 even when checks fail")
    args = ap.parse_args(argv)
    if args.max_pages < 1:
        ap.error("--max-pages must be at least 1")
    return args


def _apply_budgets(overrides: list[str]) -> None:
    for item in overrides:
        key, _, values = item.partition("=")
        warn, _, fail = values.partition(",")
        if key not in BUDGETS or not fail:
            raise SystemExit(f"bad --budget {item!r}; keys: {', '.join(BUDGETS)}")
        BUDGETS[key] = (float(warn), float(fail))


def _sign_in(page: Page, args: argparse.Namespace) -> None:
    if not (args.email and args.password):
        return
    page.goto(args.login_path)
    page.locator('input[type="email"], input[name="email"], #email').first.fill(args.email)
    page.locator('input[type="password"]').first.fill(args.password)
    page.locator('button[type="submit"]').first.click()
    page.wait_for_url(lambda url: args.login_path not in url, timeout=20_000)


def _paths(found: list[str], args: argparse.Namespace) -> list[str]:
    excluded = [re.compile(p) for p in args.exclude]
    candidates = [*args.path, *([] if args.no_discover else found)]
    seen: list[str] = []
    for path in candidates:
        if path not in seen and not any(rx.search(path) for rx in excluded):
            seen.append(path)
    return seen[: args.max_pages]


def _watch(page: Page, holder: dict[str, BrowserResult]) -> None:
    def on_console(msg: Any) -> None:
        if msg.type == "error" and "current" in holder:
            holder["current"].console_errors.append(msg.text)

    def on_error(exc: Any) -> None:
        if "current" in holder:
            holder["current"].console_errors.append(str(exc))

    def on_response(resp: Any) -> None:
        if resp.status >= 400 and "current" in holder:
            holder["current"].failed_requests.append(f"{resp.status} {resp.url}")

    page.on("console", on_console)
    page.on("pageerror", on_error)
    page.on("response", on_response)


def _load_pass(
    page: Page, paths: list[str], holder: dict[str, BrowserResult]
) -> dict[str, BrowserResult]:
    """Full document load of every path (paint timings, bytes, UX checks)."""
    results = {p: BrowserResult(path=p) for p in paths}
    for path in paths:
        holder["current"] = results[path]
        try:
            first_load(page, path, results[path])
        except Exception as exc:
            results[path].error = f"first load: {exc}"[:300]
    holder.pop("current", None)
    return results


def _nav_pass(
    page: Page,
    results: dict[str, BrowserResult],
    parents: dict[str, str],
    holder: dict[str, BrowserResult],
) -> None:
    """Client-side navigation to every path from a page that links to it."""
    known = list(results)
    for path, result in results.items():
        holder.pop("current", None)

        def attribute(result: BrowserResult = result) -> None:
            holder["current"] = result

        try:
            hubs = hubs_for(path, parents.get(path), known)
            result.nav = client_navigation(page, path, hubs, attribute)
        except Exception as exc:
            result.error = result.error or f"navigation: {exc}"[:300]
    holder.pop("current", None)


def _mobile_pass(
    context: BrowserContext, base: str, paths: list[str], results: dict[str, BrowserResult]
) -> None:
    browser = context.browser
    if browser is None:
        return
    phone = browser.new_context(
        base_url=base, viewport=PHONE, storage_state=context.storage_state()
    )
    phone.add_init_script(INIT_SCRIPT)
    page = phone.new_page()
    for path in paths:
        try:
            results[path].mobile_overflow_x = mobile_overflow(page, path)
        except Exception as exc:
            results[path].error = results[path].error or f"phone load: {exc}"[:300]
    phone.close()


def main(argv: list[str]) -> int:
    args = _args(argv)
    _apply_budgets(args.budget)
    base = args.base_url.rstrip("/")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            base_url=base, viewport=DESKTOP, storage_state=args.storage_state
        )
        context.add_init_script(INIT_SCRIPT)
        page = context.new_page()
        _sign_in(page, args)
        page.goto("/")
        settle(page)
        page_object = page.evaluate(_PAGE_OBJECT) or {}
        props = page_object.get("props") or {}
        i18n = props.get("i18n") or {}
        i18n_key = f"{i18n['locale']}:{i18n['audience']}" if i18n.get("audience") else None
        headers = inertia_headers(page_object.get("version"), i18n_key)
        paths = _paths(discover_paths(props), args)
        if not paths:
            print("No pages found: pass --path, or check the login (--email/--password).")
            return 2
        servers = [probe(context.request, base, p, headers, args.rounds) for p in paths]
        browsers: dict[str, BrowserResult] = {}
        parents: dict[str, str] = {}
        if not args.server_only:
            holder: dict[str, BrowserResult] = {}
            _watch(page, holder)
            browsers = _load_pass(page, [s.path for s in servers if not s.error], holder)
            excluded = [re.compile(x) for x in args.exclude]
            frontier = list(browsers)
            for _ in range(args.crawl_depth):
                links = {p: browsers[p].ux.get("links", []) for p in frontier}
                room = max(0, args.max_pages - len(servers))
                found = extra_pages([s.path for s in servers], links, excluded, room)
                if not found:
                    break
                parents |= found
                extra = [probe(context.request, base, p, headers, args.rounds) for p in found]
                servers += extra
                loaded = _load_pass(page, [s.path for s in extra if not s.error], holder)
                browsers |= loaded
                frontier = list(loaded)
            _nav_pass(page, browsers, parents, holder)
            if not args.no_mobile:
                _mobile_pass(context, base, list(browsers), browsers)
        browser.close()

    rows = [(s, browsers.get(s.path)) for s in servers]
    findings: list[Finding] = [f for s, b in rows for f in evaluate(s, b)]
    print(markdown(rows, findings))
    if args.json:
        dev = any(b.load.get("dev_build") for b in browsers.values())
        write_json(args.json, rows, findings, {"base_url": base, "dev_build": dev})
        print(f"\nJSON written to {args.json}")
    failed = any(f.level == "fail" for f in findings)
    return 0 if args.no_fail or not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
