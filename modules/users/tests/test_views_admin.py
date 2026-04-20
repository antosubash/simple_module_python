"""View-route tests for the admin index filter params and detail-page flags."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Admin index filter params
# ---------------------------------------------------------------------------


class TestAdminIndexFilters:
    @pytest.mark.anyio
    async def test_status_filter_in_view(self, admin_client, users_db):
        from test_api_admin import _make_user

        await _make_user(users_db, email="on-view@x.com")
        u = await _make_user(users_db, email="off-view@x.com")
        u.is_active = False
        await users_db.commit()

        resp = await admin_client.get(
            "/users/admin?status=disabled",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert resp.status_code == 200
        props = resp.json()["props"]
        emails = [u["email"] for u in props["users"]]
        assert "off-view@x.com" in emails
        assert "on-view@x.com" not in emails
        assert props["filters"]["status"] == "disabled"
        assert props["filters"]["sort"] == "email"
        assert props["filters"]["order"] == "asc"

    @pytest.mark.anyio
    async def test_filters_defaults_in_props(self, admin_client):
        resp = await admin_client.get(
            "/users/admin",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert resp.status_code == 200
        props = resp.json()["props"]
        assert "filters" in props
        assert props["filters"]["status"] == "all"
        assert props["filters"]["role"] == ""
        assert props["filters"]["verified"] == "all"
        assert props["filters"]["sort"] == "email"
        assert props["filters"]["order"] == "asc"

    @pytest.mark.anyio
    async def test_invalid_filter_values_are_ignored(self, admin_client):
        resp = await admin_client.get(
            "/users/admin?status=bad&sort=invalid&order=sideways",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert resp.status_code == 200
        props = resp.json()["props"]
        assert props["filters"]["status"] == "all"
        assert props["filters"]["sort"] == "email"
        assert props["filters"]["order"] == "asc"


# ---------------------------------------------------------------------------
# has_permissions_module flag on admin edit page
# ---------------------------------------------------------------------------


class _FakeMeta:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeModule:
    def __init__(self, name: str) -> None:
        self.meta = _FakeMeta(name)


class TestHasPermissionsModuleFlag:
    @pytest.mark.anyio
    async def test_flag_true_when_permissions_installed(self, admin_client, users_app, users_db):
        import dataclasses

        from test_api_admin import _make_user

        user = await _make_user(users_db, email="flagtest-true@example.com")

        original_sm = users_app.state.sm
        fake_mod = _FakeModule("Permissions")
        users_app.state.sm = dataclasses.replace(
            original_sm,
            modules=(*original_sm.modules, fake_mod),
        )
        try:
            resp = await admin_client.get(
                f"/users/admin/{user.id}",
                headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
            )
        finally:
            users_app.state.sm = original_sm

        assert resp.status_code == 200
        props = resp.json()["props"]
        assert props["has_permissions_module"] is True

    @pytest.mark.anyio
    async def test_flag_false_when_not_installed(self, admin_client, users_app, users_db):
        import dataclasses

        from test_api_admin import _make_user

        user = await _make_user(users_db, email="flagtest-false@example.com")

        original_sm = users_app.state.sm
        users_app.state.sm = dataclasses.replace(
            original_sm,
            modules=tuple(m for m in original_sm.modules if m.meta.name != "Permissions"),
        )
        try:
            resp = await admin_client.get(
                f"/users/admin/{user.id}",
                headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
            )
        finally:
            users_app.state.sm = original_sm

        assert resp.status_code == 200
        props = resp.json()["props"]
        assert props["has_permissions_module"] is False
