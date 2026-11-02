"""Single-tenant installs keep the stats admin-only too (#464).

The stats are administrative — user counts, installed modules, system info — so
with self sign-up on, mapping ``dashboard.view`` onto ``user`` handed them to
every account that registered. Only ``admin`` (via ``*``) holds it now; the
dashboard still renders for everyone as the post-login landing page.
"""

from __future__ import annotations

import pytest
from dashboard.constants import PERM_VIEW
from dashboard.stats import invalidate_stats_cache
from simple_module_hosting.settings import Settings
from simple_module_test.tenant_client import session_client

_STATS = "/api/dashboard/stats"
_INERTIA = {"X-Inertia": "true", "Accept": "application/json"}


@pytest.fixture(autouse=True)
def _clear_stats_cache():
    invalidate_stats_cache()
    yield
    invalidate_stats_cache()


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"multi_tenant": False, "tenant_header": ""})


def test_user_role_is_not_mapped_to_dashboard_view(app):
    assert PERM_VIEW not in app.state.sm.permissions.role_map.get("user", [])


async def _plain_user(app) -> str:
    from users.bootstrap import create_standard_user

    async with app.state.sm.db.session_factory() as session:
        result = await create_standard_user(session, email="plain@example.com", password="x" * 12)
        await session.commit()
        return str(result.user.id)


async def test_ordinary_user_is_refused_the_stats(app):
    async with session_client(app, {"user_id": await _plain_user(app)}) as c:
        resp = await c.get(_STATS)
        page = await c.get("/dashboard/", headers=_INERTIA)
    assert resp.status_code == 403
    assert page.status_code == 200
    props = page.json()["props"]
    assert props["can_view_stats"] is False
    assert props["welcome"]
    for leaked in ("total_users", "active_users_7d", "module_count", "system_info"):
        assert leaked not in props


async def test_ordinary_user_still_sees_the_dashboard_menu_entry(app):
    async with session_client(app, {"user_id": await _plain_user(app)}) as c:
        props = (await c.get("/dashboard/", headers=_INERTIA)).json()["props"]
    urls = [item["url"] for item in props["menus"]["sidebar"]]
    assert "/dashboard/" in urls


async def test_admin_still_sees_the_stats(authenticated_client):
    assert (await authenticated_client.get(_STATS)).status_code == 200
    props = (await authenticated_client.get("/dashboard/", headers=_INERTIA)).json()["props"]
    assert props["can_view_stats"] is True
    assert props["total_users"] >= 1
