"""Fixtures for the demo-account tests, shared by the seeding and guard suites.

Loaded as a pytest plugin from ``conftest.py`` — same mechanism as
``_middleware_support``. Not named ``test_*`` so pytest does not collect it.
"""

from __future__ import annotations

import httpx
import pytest
from _users_app_builders import _build_users_app
from users.demo import ensure_demo_user

DEMO_EMAIL = "demo@example.com"


@pytest.fixture
async def demo_app(monkeypatch):
    """A users app with demo mode on and the demo account seeded."""
    application, ctx = await _build_users_app(monkeypatch, allow_signup=False)
    application.state.users.settings.demo_mode = True
    await ensure_demo_user(application)
    yield application
    await ctx.__aexit__(None, None, None)


@pytest.fixture
async def demo_client(demo_app):
    """Anonymous client against ``demo_app`` — it signs itself in via the button."""
    transport = httpx.ASGITransport(app=demo_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
