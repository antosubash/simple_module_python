"""The /setup wizard's HTTP surface.

``test_setup_closes_after_completion`` is the security-relevant one. Every
route here is unauthenticated by necessity — the wizard exists precisely when
no account exists — and one of them can run Alembic. What bounds that is the
routes refusing once an administrator exists, so it is asserted rather than
assumed.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.anyio


def _mount(app):
    from host.routes_setup import router as setup_router

    app.include_router(setup_router)
    return app


async def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


async def test_setup_reachable_without_auth(setup_pending_app) -> None:
    async with await _client(_mount(setup_pending_app)) as client:
        resp = await client.get("/setup", follow_redirects=False)

    assert resp.status_code == 200


async def test_connection_checks_are_reported(setup_pending_app) -> None:
    """The wizard reports each dependency by name with a reason attached."""
    async with await _client(_mount(setup_pending_app)) as client:
        resp = await client.post("/setup/test-connections")

    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()["checks"]}
    assert names == {"host.database", "background_tasks.redis"}


async def test_creating_an_admin_completes_setup(setup_pending_app) -> None:
    app = _mount(setup_pending_app)
    async with await _client(app) as client:
        resp = await client.post(
            "/setup/administrator",
            json={"email": "root@example.com", "password": "SetupPass1!"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["created"] is True

        # The gate must now release for ordinary routes.
        after = await client.get("/", follow_redirects=False)

    assert after.status_code != 302


async def test_setup_closes_after_completion(app) -> None:
    """Once an administrator exists every /setup route refuses.

    This is what bounds /setup/migrations — an unauthenticated endpoint that
    can execute Alembic. It must be unreachable on a configured install.
    """
    async with await _client(_mount(app)) as client:
        for method, path in (
            ("GET", "/setup"),
            ("POST", "/setup/test-connections"),
            ("POST", "/setup/migrations"),
            ("POST", "/setup/site-basics"),
        ):
            resp = await client.request(method, path, json={})
            assert resp.status_code == 404, f"{method} {path} answered {resp.status_code}"


async def test_administrator_route_closes_after_completion(app) -> None:
    """The sharpest one: an open admin-creation form on a live install."""
    async with await _client(_mount(app)) as client:
        resp = await client.post(
            "/setup/administrator",
            json={"email": "intruder@example.com", "password": "Whatever1!"},
        )

    assert resp.status_code == 404


async def test_administrator_route_stays_closed_when_only_migrations_pend(app, monkeypatch) -> None:
    """A behind-head schema must not reopen admin creation.

    ``create_app`` registers ``host.migrations`` for every install, so a live
    deployment that ships code ahead of its migration job re-enters setup mode
    with its administrators intact. Gating this route on "setup mode" rather
    than on its own step would hand an anonymous request a fresh superuser
    there — the routes must be gated per step, not per mode.
    """
    behind = {
        "current_revision": "abc123",
        "head_revision": "def456",
        "is_current": False,
        "pending_count": 1,
    }
    app.state.migration = behind

    # The gate re-reads a behind-head verdict from the database rather than
    # trusting the boot snapshot, so the stub has to keep saying "behind".
    async def _still_behind(*_args, **_kwargs):
        return dict(behind)

    monkeypatch.setattr(
        "simple_module_hosting.migrations.migration_status", _still_behind, raising=True
    )

    async with await _client(_mount(app)) as client:
        # The wizard itself opens — the schema really is behind and that is
        # what it is for.
        assert (await client.post("/setup/test-connections")).status_code == 200

        resp = await client.post(
            "/setup/administrator",
            json={"email": "intruder@example.com", "password": "Whatever1!"},
        )

    assert resp.status_code == 404


async def test_administrator_route_enforces_a_password_policy(setup_pending_app) -> None:
    """``create_admin`` writes the hash directly, bypassing ``UserManager``."""
    async with await _client(_mount(setup_pending_app)) as client:
        resp = await client.post(
            "/setup/administrator",
            json={"email": "root@example.com", "password": "short"},
        )

    assert resp.status_code == 422
