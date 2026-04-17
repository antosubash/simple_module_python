"""Locust load-test scenarios.

Run via ``make loadtest`` (requires a server already running at :8000,
e.g. ``make dev``) or ``make loadtest-memray`` which starts a profiled
uvicorn, runs this file headless, shuts down, and emits a flamegraph.

Two user classes are defined. Locust runs **all** ``HttpUser`` subclasses
by default; filter with ``--class-picker`` or ``--tags`` if you only want
one:

* :class:`AnonymousUser` — hits unauthenticated paths that redirect to
  ``/users/login``. Useful for profiling middleware and the login page
  render. Always enabled.
* :class:`AuthedUser` — seeded via ``scripts/loadtest_seed.py``. Only
  activates when ``SM_LOADTEST_COOKIE`` and ``SM_LOADTEST_CSRF`` are
  exported in the environment. Otherwise it disables itself so anonymous
  runs still work. Drives real product-service code paths.
"""

from __future__ import annotations

import os

from locust import HttpUser, between, tag, task

_COOKIE = os.environ.get("SM_LOADTEST_COOKIE")
_CSRF = os.environ.get("SM_LOADTEST_CSRF")


@tag("anon")
class AnonymousUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(3)
    def browse_products(self) -> None:
        self.client.get("/products/", name="anon GET /products/")

    @task(1)
    def readiness(self) -> None:
        self.client.get("/health/ready", name="anon GET /health/ready")


@tag("authed")
class AuthedUser(HttpUser):
    wait_time = between(0.1, 0.5)

    # ``abstract = True`` when credentials are missing so locust skips spawning
    # this class rather than sending anonymous traffic that redirects.
    abstract = not (_COOKIE and _CSRF)

    def on_start(self) -> None:
        self.client.cookies.set("session", _COOKIE)
        self.client.headers["X-CSRF-Token"] = _CSRF

    @task(5)
    def browse_products_page(self) -> None:
        self.client.get("/products/", name="auth GET /products/ (inertia)")

    @task(3)
    def list_products_api(self) -> None:
        self.client.get("/api/products/", name="auth GET /api/products/")

    @task(1)
    def dashboard(self) -> None:
        self.client.get("/", name="auth GET / (dashboard)")
