"""Locust load scenario: realistic authenticated browse traffic.

Auth uses the forged session cookie minted by ``scripts/loadtest_seed.py``
(exported as ``SM_LOADTEST_COOKIE``) — this skips the login flow and its rate
limiter so the profile reflects steady-state authenticated traffic. That cookie
authenticates the middleware/permission path; ``/api/users/me`` (fastapi-users
token-only) is intentionally not exercised here.

Drive it via ``make loadtest`` (server already running) or ``make loadtest-memray``
(starts uvicorn under memray). Seed realistic data first with ``make loadtest-seed``
so the list/search/pagination endpoints hit real volumes.
"""

from __future__ import annotations

import json
import os
import random
from html.parser import HTMLParser

from locust import HttpUser, between, task
from locust.exception import StopUser

_COOKIE = os.environ.get("SM_LOADTEST_COOKIE", "")
_SEARCH_TERMS = ("john", "smith", "maria", "lee", "garcia", "son", "er", "a")


class _PageParser(HTMLParser):
    """Read the v3 client's JSON script, including split parser data chunks."""

    def __init__(self) -> None:
        super().__init__()
        self.in_page = False
        self.chunks: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        self.in_page = tag == "script" and dict(attrs).get("data-page") == "app"

    def handle_endtag(self, tag) -> None:
        if tag == "script":
            self.in_page = False

    def handle_data(self, data) -> None:
        if self.in_page:
            self.chunks.append(data)


class AuthedUser(HttpUser):
    """Authenticated browser-like user driving a weighted endpoint mix."""

    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        if not _COOKIE:
            raise RuntimeError(
                'SM_LOADTEST_COOKIE is unset — run `eval "$(uv run python '
                'scripts/loadtest_seed.py)"` first (make loadtest-memray does this).'
            )
        self.client.cookies.set("session", _COOKIE)
        with self.client.get(
            "/dashboard/",
            headers={"Accept": "text/html"},
            name="/dashboard/ (initial HTML)",
            catch_response=True,
        ) as response:
            try:
                if response.status_code != 200:
                    raise ValueError(f"Initial HTML returned {response.status_code}")
                parser = _PageParser()
                parser.feed(response.text)
                page = json.loads("".join(parser.chunks))
                version = page["version"]
                catalog = page["props"]["i18n"]
                if not isinstance(version, str) or not version:
                    raise ValueError("Initial page has no asset version")
                if (
                    not isinstance(catalog, dict)
                    or not isinstance(catalog.get("messages"), dict)
                    or catalog.get("audience") != "full"
                    or not isinstance(catalog.get("locale"), str)
                    or not catalog["locale"]
                ):
                    raise ValueError("Initial page has no authenticated catalog")
                self._inertia = {
                    "X-Inertia": "true",
                    "X-Inertia-Version": version,
                    "X-SM-I18n": f"{catalog['locale']}:{catalog['audience']}",
                }
            except (ValueError, KeyError, TypeError) as exc:
                response.failure(f"Cannot initialize browser: {exc}")
                raise StopUser from exc

    def _visit(self, path: str, name: str) -> None:
        with self.client.get(
            path, headers=self._inertia, name=name, catch_response=True
        ) as response:
            if response.status_code == 409:
                response.failure("Inertia asset version conflict; restart the load test")

    # Weights approximate a real admin browsing session: lots of list/detail
    # reads, fewer dashboard hits. `name=` groups stats so paginated URLs with
    # varying query strings don't explode the Locust stats table.
    @task(10)
    def dashboard_view(self) -> None:
        self._visit("/dashboard/", "/dashboard/")

    @task(5)
    def dashboard_stats(self) -> None:
        self.client.get("/api/dashboard/stats", name="/api/dashboard/stats")

    @task(18)
    def users_list_api(self) -> None:
        page = random.randint(1, 50)
        self.client.get(f"/api/users/admin?page={page}&per_page=20", name="/api/users/admin")

    @task(10)
    def users_list_view(self) -> None:
        page = random.randint(1, 50)
        self._visit(f"/admin/users/?page={page}&per_page=20", "/admin/users/")

    @task(8)
    def users_search(self) -> None:
        term = random.choice(_SEARCH_TERMS)
        self.client.get(f"/api/users/admin?q={term}&page=1&per_page=20", name="/api/users/admin?q")

    @task(16)
    def audit_list(self) -> None:
        page = random.randint(1, 200)
        self.client.get(f"/api/audit_log/?page={page}&page_size=20", name="/api/audit_log/")

    @task(5)
    def settings_modules(self) -> None:
        self.client.get("/api/settings/modules", name="/api/settings/modules")

    @task(3)
    def permissions(self) -> None:
        self.client.get("/api/permissions/", name="/api/permissions/")

    @task(3)
    def feature_flags(self) -> None:
        self.client.get("/api/feature_flags/", name="/api/feature_flags/")
