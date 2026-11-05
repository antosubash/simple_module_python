"""The pure parts of the page-perf skill's audit script.

The script ships inside ``skills/simple-module-page-perf`` (bundled with the
CLI), so it is tested here: URL patterns and crawl sampling, Server-Timing
parsing, page description and the budget verdicts. The browser half needs a
running app and is exercised by running the audit itself.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytest.importorskip("playwright")

_SCRIPTS = Path(__file__).resolve().parents[3] / "skills/simple-module-page-perf/scripts/page_audit"
sys.path.insert(0, str(_SCRIPTS))

import audit_crawl  # noqa: E402
import audit_report  # noqa: E402
import audit_server  # noqa: E402
from audit_browser import BrowserResult  # noqa: E402

_UUID = "91a1b900-5c0c-45c8-9e0c-894d78f7c425"


class TestCrawl:
    def test_ids_collapse_to_one_pattern(self) -> None:
        assert audit_crawl.pattern(f"/admin/users/{_UUID}/edit?tab=2") == "/admin/users/:id/edit"
        assert audit_crawl.pattern("/orders/42") == "/orders/:id"
        assert audit_crawl.pattern("/admin/settings/store") == "/admin/settings/store"

    def test_one_sample_per_pattern(self) -> None:
        links = {"/admin/users/": [f"/admin/users/{_UUID}", "/admin/users/7", "/admin/users/add"]}
        found = audit_crawl.extra_pages(["/admin/users/"], links, [], 10)
        assert found == {
            f"/admin/users/{_UUID}": "/admin/users/",
            "/admin/users/add": "/admin/users/",
        }

    def test_a_covered_section_is_sampled_from_its_own_pages(self) -> None:
        """An audit row linking into settings is a worse sample than settings' own list."""
        links = {
            "/admin/audit-log/": [f"/admin/settings/{_UUID}/edit"],
            "/admin/settings/store": ["/admin/settings/1/edit"],
        }
        known = ["/admin/audit-log/", "/admin/settings/store"]
        found = audit_crawl.extra_pages(known, links, [], 10)
        assert found == {"/admin/settings/1/edit": "/admin/settings/store"}

    def test_excluded_links_and_the_limit(self) -> None:
        links = {"/a/": ["/a/logout", "/a/1", "/a/x/y", "/a/z"]}
        excluded = [re.compile("logout")]
        assert list(audit_crawl.extra_pages(["/a/"], links, excluded, 2)) == ["/a/1", "/a/x/y"]

    def test_hubs_prefer_parent_then_same_area_then_home(self) -> None:
        known = ["/dashboard/", "/admin/sharing/", "/admin/users/"]
        assert audit_crawl.hubs_for("/admin/users/", None, known) == ["/admin/sharing/", "/"]
        assert audit_crawl.hubs_for("/admin/users/7", "/admin/users/", known) == [
            "/admin/users/",
            "/admin/sharing/",
            "/",
        ]


class TestServer:
    def test_server_timing_is_parsed(self) -> None:
        header = 'app;dur=12.4, db;dur=3.1;desc="5 queries"'
        assert audit_server._timing(header) == (12.4, 3.1, 5)
        assert audit_server._timing(None) == (None, None, None)

    def test_menu_urls_are_discovered(self) -> None:
        props = {
            "menus": {
                "sidebar": [{"url": "/orders/", "children": [{"url": "/orders/new"}]}],
                "admin": [{"href": "/admin/x/"}, {"url": "https://elsewhere.test/"}],
            }
        }
        assert audit_server.discover_paths(props) == ["/orders/", "/orders/new", "/admin/x/"]

    def test_page_description_separates_shared_and_deferred_props(self) -> None:
        result = audit_server.ServerResult(path="/orders/")
        page = {
            "component": "Orders/Index",
            "props": {
                "auth": {"user": None},
                "i18n": {"locale": "en", "messages": {"a": "b"}},
                "rows": [{"id": i} for i in range(50)],
                "filters": {},
            },
            "deferredProps": {"stats": ["totals", "chart"]},
            "mergeProps": ["rows"],
        }
        audit_server._describe_page(result, page)
        assert result.component == "Orders/Index"
        assert result.top_props[0][0] == "rows"
        assert "auth" not in dict(result.top_props)
        assert result.i18n_bytes > 0
        assert result.deferred == ["chart", "totals"]
        assert result.merge == ["rows"]


def _server(**over) -> audit_server.ServerResult:
    base = {"path": "/p/", "app_ms": 10.0, "queries": 3, "json_bytes": 2048}
    return audit_server.ServerResult(**{**base, **over})


def _checks(findings) -> dict[str, str]:
    return {f.check: f.level for f in findings}


class TestBudgets:
    def test_a_fast_small_page_is_clean(self) -> None:
        assert audit_report.evaluate(_server(), None) == []

    def test_warn_and_fail_thresholds(self) -> None:
        checks = _checks(audit_report.evaluate(_server(app_ms=150.0, queries=40), None))
        assert checks == {"app_ms": "warn", "queries": "fail"}

    def test_the_i18n_catalog_does_not_count_against_the_page(self) -> None:
        big = _server(json_bytes=400 * 1024, i18n_bytes=390 * 1024)
        assert audit_report.evaluate(big, None) == []

    def test_redirects_and_server_errors(self) -> None:
        redirected = _server(redirected=True, final_url="http://t/p/")
        assert _checks(audit_report.evaluate(redirected, None)) == {"redirect": "warn"}
        broken = _server(error="HTTP 500 (not an Inertia page response)")
        assert _checks(audit_report.evaluate(broken, None)) == {"server": "fail"}

    def test_bundle_budgets_only_apply_to_a_production_build(self) -> None:
        load = {"lcp_ms": 5000, "js_bytes": 900 * 1024, "cls": 0}
        dev = BrowserResult(path="/p/", load={**load, "dev_build": True})
        prod = BrowserResult(path="/p/", load={**load, "dev_build": False})
        assert _checks(audit_report.evaluate(_server(), dev)) == {}
        assert _checks(audit_report.evaluate(_server(), prod)) == {
            "lcp_ms": "fail",
            "js_kb": "fail",
        }

    def test_ux_checks(self) -> None:
        browser = BrowserResult(
            path="/p/",
            load={"cls": 0.3, "dev_build": True},
            ux={"dom_nodes": 2000, "stuck_loaders": 1, "unnamed_controls": 2, "h1_count": 0},
            mobile_overflow_x=40,
            console_errors=["TypeError: x is undefined"],
        )
        assert _checks(audit_report.evaluate(_server(), browser)) == {
            "cls": "fail",
            "dom_nodes": "warn",
            "console": "fail",
            "overflow": "warn",
            "stuck_loaders": "warn",
            "unnamed_controls": "warn",
            "h1": "warn",
        }
