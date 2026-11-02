"""The dashboard is platform-only: its stats span every tenant (#374).

``User`` is not tenant-scoped, so ``total_users`` counts the whole install. The
stats therefore need ``dashboard.view``, which only the platform ``admin``
(wildcard) holds and no tenant role is mapped to.
"""

from __future__ import annotations

import pytest
from dashboard.constants import PERM_VIEW
from dashboard.stats import invalidate_stats_cache
from simple_module_core.tenancy import TenantRole, tenant_role

_STATS = "/api/dashboard/stats"
_INERTIA = {"X-Inertia": "true", "Accept": "application/json"}


@pytest.fixture(autouse=True)
def _clear_stats_cache():
    invalidate_stats_cache()
    yield
    invalidate_stats_cache()


def test_permission_is_registered_and_mapped_to_no_tenant_role(app):
    registry = app.state.sm.permissions
    assert registry.has(PERM_VIEW)
    for role in TenantRole:
        assert PERM_VIEW not in registry.role_map[tenant_role(role)]


def test_user_role_is_not_mapped_when_multi_tenant(app):
    """Every tenant member holds ``user``; mapping it would leak the counts."""
    assert app.state.sm.settings.multi_tenant
    assert PERM_VIEW not in app.state.sm.permissions.role_map.get("user", [])


async def test_anonymous_is_refused(client):
    resp = await client.get(_STATS, follow_redirects=False)
    assert resp.status_code in (302, 401, 403)


@pytest.mark.parametrize("role", list(TenantRole))
async def test_tenant_member_is_forbidden(tenant_client, role):
    async with tenant_client(role) as m:
        resp = await m.client.get(_STATS)
    assert resp.status_code == 403
    assert PERM_VIEW in resp.json()["detail"]


async def test_admin_sees_the_stats(authenticated_client):
    resp = await authenticated_client.get(_STATS)
    assert resp.status_code == 200
    assert resp.json()["total_users"] >= 1


async def test_a_warm_cache_does_not_open_the_api_to_a_tenant_member(
    authenticated_client, tenant_client
):
    assert (await authenticated_client.get(_STATS)).status_code == 200  # warms the cache
    async with tenant_client() as m:
        assert (await m.client.get(_STATS)).status_code == 403


async def test_home_page_for_admin_carries_the_stats(authenticated_client):
    props = (await authenticated_client.get("/dashboard/", headers=_INERTIA)).json()["props"]
    assert props["can_view_stats"] is True
    assert props["total_users"] >= 1
    assert "system_info" in props


async def test_home_page_for_a_tenant_member_renders_without_stats(tenant_client):
    """``/dashboard/`` is the post-login landing page: it must not 403 or leak."""
    async with tenant_client("member") as m:
        resp = await m.client.get("/dashboard/", headers=_INERTIA)
    assert resp.status_code == 200
    props = resp.json()["props"]
    assert props["can_view_stats"] is False
    assert props["welcome"]
    for leaked in ("total_users", "active_users_7d", "module_count", "system_info"):
        assert leaked not in props
