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

    @pytest.mark.anyio
    async def test_page_past_the_end_clamps_to_last_page(self, admin_client, users_db):
        """A stale/hand-edited ?page= beyond the last page must clamp and
        return the last page's rows, not an empty list with a nonzero total —
        the same bug class background_tasks and file_storage fix for their
        own admin listings."""
        from test_api_admin import _make_user

        await _make_user(users_db, email="clamp-a@x.com")
        await _make_user(users_db, email="clamp-b@x.com")

        resp = await admin_client.get(
            "/users/admin?page=999&per_page=1",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert resp.status_code == 200
        props = resp.json()["props"]
        assert props["users"], "expected the clamped last page to carry rows"
        assert props["pagination"]["page"] < 999
        assert props["pagination"]["total"] >= 2

    @pytest.mark.anyio
    async def test_pagination_prop_echoes_clamped_values(self, admin_client, users_db):
        """The pagination prop must carry the values the query actually ran
        with — ?page=0 renders page-1 rows and must not be labelled page 0,
        and an oversized per_page is bounded to what the service fetched."""
        from test_api_admin import _make_user

        await _make_user(users_db, email="clamp-c@x.com")

        resp = await admin_client.get(
            "/users/admin?page=0&per_page=1000",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert resp.status_code == 200
        pagination = resp.json()["props"]["pagination"]
        assert pagination["page"] == 1
        assert pagination["per_page"] == 200


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


# ---------------------------------------------------------------------------
# Admin add-people page (create + invite merged behind a mode switch)
# ---------------------------------------------------------------------------


class TestAdminAddPeoplePage:
    @pytest.mark.anyio
    async def test_add_page_renders_with_roles(self, admin_client):
        resp = await admin_client.get(
            "/users/admin/add",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["component"] == "Users/Users/AddPeople"
        assert "roles" in data["props"]

    @pytest.mark.anyio
    async def test_add_page_reports_whether_mail_can_be_delivered(self, admin_client):
        """Drives the copy-link panel — the page has to know before submitting."""
        resp = await admin_client.get(
            "/users/admin/add",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert "mailer_delivers" in resp.json()["props"]

    @pytest.mark.anyio
    async def test_no_mailer_does_not_promise_delivery(self, admin_client, app):
        """With nothing able to send, the page must offer the copy-link panel —
        claiming delivery is the one answer that is certainly wrong."""
        original = app.state.users.mailer
        app.state.users.mailer = None
        try:
            resp = await admin_client.get(
                "/users/admin/add",
                headers={"X-Inertia": "true", "Accept": "application/json"},
            )
            assert resp.json()["props"]["mailer_delivers"] is False
        finally:
            app.state.users.mailer = original

    @pytest.mark.anyio
    async def test_add_page_requires_auth(self, anon_client):
        resp = await anon_client.get("/users/admin/add", follow_redirects=False)
        assert resp.status_code == 302

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("old_path", "mode"),
        [("/users/admin/create", "create"), ("/users/admin/invite", "invite")],
    )
    async def test_old_urls_redirect_into_the_right_mode(self, admin_client, old_path, mode):
        """Existing links must land on the merged form with their mode preselected."""
        resp = await admin_client.get(old_path, follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == f"/users/admin/add?mode={mode}"
