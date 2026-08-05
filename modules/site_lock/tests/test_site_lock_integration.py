"""Boot-level wiring for the site_lock module.

The unit tests in ``test_site_lock_middleware.py`` drive the middleware in a
hand-built ASGI stack. These exercise the real ``create_app`` pipeline so a
regression in discovery, settings registration, or middleware ordering is
caught even though every unit test would still pass.
"""

from __future__ import annotations

import pytest
from site_lock import constants as c
from site_lock.settings import SiteLockSettings


def test_module_state_is_mounted_and_disabled_by_default(app) -> None:
    """The off-by-default guarantee, asserted against a really-booted app."""
    state = getattr(app.state, c.MODULE_PACKAGE)
    assert state.settings.enabled is False


def test_site_lock_middleware_runs_before_auth(app) -> None:
    """Ordering is load-bearing: if Auth ran first, anonymous visitors would
    be redirected to the login page instead of seeing the gate."""
    names = [m.cls.__name__ for m in app.user_middleware]
    assert names.index("SiteLockMiddleware") < names.index("AuthMiddleware")


def test_settings_are_registered_for_the_admin_ui(app) -> None:
    registry = app.state.settings.module_registry
    assert registry.get(c.MODULE_PACKAGE) is SiteLockSettings


async def test_disabled_gate_does_not_interfere(client) -> None:
    """With the gate off the request reaches the app untouched.

    The test host mounts no landing route, so a 404 here is the *app's* own
    answer — the point is that it is not a 302 to the gate.
    """
    response = await client.get("/", follow_redirects=False)
    assert response.status_code != 302
    assert c.UNLOCK_PATH not in response.headers.get("location", "")


@pytest.fixture
def locked(app):
    """Turn the gate on the way the settings UI does, then restore it."""
    state = getattr(app.state, c.MODULE_PACKAGE)
    original = state.settings
    state.settings = SiteLockSettings(enabled=True, password="pw")
    yield
    state.settings = original


async def test_locked_site_gates_the_landing_page(client, locked) -> None:
    response = await client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith(c.UNLOCK_PATH)


async def test_locked_site_still_answers_health_probes(client, locked) -> None:
    response = await client.get("/health")
    assert response.status_code == 200


async def test_locked_site_serves_the_gate_page(client, locked) -> None:
    response = await client.get(c.UNLOCK_PATH)
    assert response.status_code == 200
    assert 'name="password"' in response.text


async def test_locked_site_returns_json_for_api_routes(client, locked) -> None:
    response = await client.get("/api/users/me", follow_redirects=False)
    assert response.status_code == 403
    assert response.json() == {"detail": "Site is locked"}
