"""Fixtures for end-to-end browser tests.

These tests drive a real Chromium browser against a running stack
(`make docker-up` + `make dev`). They are gated by the ``e2e`` pytest marker
(declared in ``pyproject.toml``) and excluded from the default suite.

Env vars:
    E2E_BASE_URL  — where the FastAPI host is listening (default: http://localhost:8000)
    E2E_USERNAME  — admin email address (default: admin@example.com)
    E2E_PASSWORD  — admin password (default: admin)
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("E2E_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def e2e_username() -> str:
    return os.environ.get("E2E_USERNAME", "admin@example.com")


@pytest.fixture(scope="session")
def e2e_password() -> str:
    return os.environ.get("E2E_PASSWORD", "admin")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, base_url):
    """Override pytest-playwright's context args to set base_url.

    With this in place, ``page.goto("/")`` resolves relative to E2E_BASE_URL.
    """
    return {**browser_context_args, "base_url": base_url}
