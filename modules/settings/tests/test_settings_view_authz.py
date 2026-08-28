"""The settings screens must be as guarded as the API behind them.

``/api/settings/modules`` has always required ``settings.view``, but the Inertia
screens rendering the same data carried no permission dependency — so any
signed-in account could read every module's configuration (values, env var
names, and which of the two is in force) by asking for the page instead.
"""

from __future__ import annotations

import httpx
import pytest
from simple_module_test.fixtures import forge_session_cookie

_VIEW_ROUTES = ["/admin/settings/", "/admin/settings/store", "/admin/settings/create"]


@pytest.fixture
async def plain_user_client(app):
    """A signed-in account holding no settings permission."""
    from users.models import User

    async with app.state.sm.db.session_factory() as session:
        user = User(
            email="plain@example.com",
            hashed_password="x",
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.commit()
        user_id = str(user.id)

    signed = forge_session_cookie(app.state.sm.settings.secret_key, {"user_id": user_id})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies={"session": signed}
    ) as client:
        yield client


@pytest.mark.parametrize("path", _VIEW_ROUTES)
async def test_view_routes_reject_a_user_without_settings_view(
    plain_user_client: httpx.AsyncClient, path: str
):
    resp = await plain_user_client.get(path, follow_redirects=False)
    assert resp.status_code in (302, 401, 403), resp.text[:400]


async def test_the_api_and_the_screen_agree(plain_user_client: httpx.AsyncClient):
    """Same data, same answer — the gap between them was the bug."""
    api = await plain_user_client.get("/api/settings/modules", follow_redirects=False)
    view = await plain_user_client.get("/admin/settings/", follow_redirects=False)
    assert api.status_code in (302, 401, 403)
    assert view.status_code in (302, 401, 403)


@pytest.mark.parametrize("path", _VIEW_ROUTES)
async def test_admins_still_reach_every_screen(authenticated_client: httpx.AsyncClient, path: str):
    resp = await authenticated_client.get(path, follow_redirects=False)
    assert resp.status_code == 200, resp.text[:400]
