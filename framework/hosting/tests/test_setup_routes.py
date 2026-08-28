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
