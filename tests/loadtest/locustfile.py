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

import os
import random

from locust import HttpUser, between, task

_COOKIE = os.environ.get("SM_LOADTEST_COOKIE", "")
_INERTIA = {"X-Inertia": "true"}
_SEARCH_TERMS = ("john", "smith", "maria", "lee", "garcia", "son", "er", "a")


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

    # Weights approximate a real admin browsing session: lots of list/detail
    # reads, fewer dashboard hits. `name=` groups stats so paginated URLs with
    # varying query strings don't explode the Locust stats table.
    @task(10)
    def dashboard_view(self) -> None:
        self.client.get("/dashboard/", headers=_INERTIA, name="/dashboard/")

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
        self.client.get(
            f"/admin/users/?page={page}&per_page=20", headers=_INERTIA, name="/admin/users/"
        )

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
