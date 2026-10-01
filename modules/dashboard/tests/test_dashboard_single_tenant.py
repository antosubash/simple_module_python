"""Single-tenant installs keep the stats for ordinary users (review of #374).

With ``multi_tenant`` off there is one tenant — the install — so the counts
leak nothing, and every signed-in ``user`` had them before ``dashboard.view``
existed. With it on, every tenant member also holds ``user``, so the mapping
must not be made there (``test_dashboard_permission.py``).
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


def test_user_role_is_mapped_to_dashboard_view(app):
    assert PERM_VIEW in app.state.sm.permissions.role_map["user"]


async def _plain_user(app) -> str:
    from users.bootstrap import create_standard_user

    async with app.state.sm.db.session_factory() as session:
        result = await create_standard_user(session, email="plain@example.com", password="x" * 12)
        await session.commit()
        return str(result.user.id)


async def test_ordinary_user_sees_the_stats(app):
    async with session_client(app, {"user_id": await _plain_user(app)}) as c:
        assert (await c.get(_STATS)).status_code == 200
        props = (await c.get("/dashboard/", headers=_INERTIA)).json()["props"]
    assert props["can_view_stats"] is True
    assert props["total_users"] >= 1
