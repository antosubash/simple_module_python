"""Who may open the ``/admin`` overview.

The page lists whatever is in the viewer's ``adminSidebar``, which the menu
registry filters by roles *and* permissions. Admission has to follow the same
rule: gating on the ``admin`` role alone meant a custom role holding a single
admin permission could reach the screen that permission unlocks, see the
AdminLayout badge pointing at ``/admin``, and get a 403 from a page that would
have listed exactly the one tool they can use.

The route ships with ``simple_module_hosting`` (GH #914), so the plain
``app`` fixture serves it; these tests live here because they sign in through
the ``users`` module.
"""

from __future__ import annotations

import httpx
import pytest
from simple_module_hosting.admin_overview import PAGE_OVERVIEW
from simple_module_test import inertia_page
from simple_module_test.fixtures import forge_session_cookie


async def _client_for(app, *, email: str, roles: list[str], permissions: list[str]):
    """Sign in an account holding exactly these roles and permissions."""
    from sqlalchemy import select
    from users.models import User, UserRole
    from users.models.role import Role

    async with app.state.sm.db.session_factory() as session:
        user = User(email=email, hashed_password="x", is_active=True, is_verified=True)
        session.add(user)
        await session.flush()
        for role_name in roles:
            # Get-or-create: the `app` fixture seeds an administrator so the
            # first-run setup gate releases, and that already creates the
            # 'admin' Role. Role.name is unique, so blindly inserting collides.
            role = (
                await session.execute(select(Role).where(Role.name == role_name))
            ).scalar_one_or_none()
            if role is None:
                role = Role(name=role_name)
                session.add(role)
                await session.flush()
            session.add(UserRole(user_id=user.id, role_id=role.id))
        user_id = str(user.id)
        await session.commit()

    if permissions:
        registry = app.state.sm.permissions
        for role_name in roles:
            registry.map_role(role_name, permissions)

    signed = forge_session_cookie(app.state.sm.settings.secret_key, {"user_id": user_id})
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies={"session": signed}
    )


@pytest.mark.anyio
async def test_admin_reaches_the_overview(app) -> None:
    client = await _client_for(app, email="root@example.com", roles=["admin"], permissions=[])
    async with client:
        resp = await client.get("/admin", follow_redirects=False)
    assert resp.status_code == 200, resp.text
    assert inertia_page(resp).component == PAGE_OVERVIEW


@pytest.mark.anyio
async def test_admin_reaches_it_even_with_an_empty_sidebar(app) -> None:
    """An install with no admin modules must still reach the page's own empty
    state — 403'ing there would make that copy unreachable."""
    from simple_module_core.menu import MenuSection

    registry = app.state.sm.menu_registry
    registry._items = [i for i in registry._items if i.section != MenuSection.ADMIN_SIDEBAR]
    registry._sorted = None
    client = await _client_for(
        app, email="lonely-admin@example.com", roles=["admin"], permissions=[]
    )
    async with client:
        resp = await client.get("/admin", follow_redirects=False)
    assert resp.status_code == 200, resp.text


@pytest.mark.anyio
async def test_account_with_no_admin_entries_is_refused(app) -> None:
    """A plain signed-in user has an empty admin sidebar — nothing to show."""
    client = await _client_for(app, email="plain@example.com", roles=[], permissions=[])
    async with client:
        resp = await client.get("/admin", follow_redirects=False)
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_permission_holder_without_the_admin_role_is_admitted(app) -> None:
    """The case the role-only gate got wrong.

    This account can open ``/admin/settings/`` on its ``settings.view`` grant,
    so refusing it the overview that links there is self-contradictory.
    """
    from settings.core.constants import PERM_VIEW

    client = await _client_for(
        app,
        email="settings-only@example.com",
        roles=["settings-reader"],
        permissions=[PERM_VIEW],
    )
    async with client:
        resp = await client.get("/admin", follow_redirects=False)
    assert resp.status_code == 200, resp.text


@pytest.mark.anyio
async def test_anonymous_is_bounced_to_login(app) -> None:
    """AuthMiddleware owns this half — a 403 here would leak that /admin exists."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        resp = await c.get("/admin", follow_redirects=False)
    assert resp.status_code == 302
    assert "/users/login" in resp.headers["location"]
