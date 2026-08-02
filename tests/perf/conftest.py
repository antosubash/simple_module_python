"""Fixtures for the navigation performance benchmark.

Drives a real browser against a running stack. Gated by BOTH the ``perf`` and
``e2e`` markers, so the default suite (``-m 'not e2e and not perf'``) skips it
and ``make bench`` (which targets ``tests/benchmarks``) doesn't pick it up
either. Drive it with ``make bench-nav``.

Env vars:
    PERF_BASE_URL  — where the host is listening (default: http://localhost:8000)
    PERF_USERNAME  — admin email (default: admin@example.com)
    PERF_PASSWORD  — admin password (default: admin)
    PERF_BUILD     — label recorded in the report: "dev" or "prod"
    PERF_ROUNDS    — navigations per route (default: 20)
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page

DEFAULT_ROUNDS = 20
_LOGIN_TIMEOUT_MS = 20_000


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("PERF_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def perf_username() -> str:
    return os.environ.get("PERF_USERNAME", "admin@example.com")


@pytest.fixture(scope="session")
def perf_password() -> str:
    return os.environ.get("PERF_PASSWORD", "admin")


@pytest.fixture(scope="session")
def perf_build() -> str:
    """Label for the build under test — recorded alongside the numbers.

    Dev and prod are measured separately because Vite's dev-mode transform
    round-trip is a real cost in dev that does not ship to users.
    """
    return os.environ.get("PERF_BUILD", "dev")


@pytest.fixture(scope="session")
def perf_rounds() -> int:
    return int(os.environ.get("PERF_ROUNDS", str(DEFAULT_ROUNDS)))


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, base_url):
    """Resolve ``page.goto("/")`` against PERF_BASE_URL."""
    return {**browser_context_args, "base_url": base_url}


@pytest.fixture
def logged_in_page(page: Page, perf_username: str, perf_password: str) -> Page:
    """A page authenticated as the admin, parked on the dashboard."""
    page.goto("/")
    page.get_by_role("link", name="Log in").first.click()
    page.locator("#email").fill(perf_username)
    page.locator("#password").fill(perf_password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url("**/dashboard/**", timeout=_LOGIN_TIMEOUT_MS)
    return page
