"""View-route tests for the users module (Inertia endpoints)."""

from __future__ import annotations

import uuid

import pytest
from fastapi_users.password import PasswordHelper
from users.models import Role, User, UserRole

_pw = PasswordHelper()


def _hash(plain: str) -> str:
    return _pw.hash(plain)


async def _make_verified_user(
    session,
    email: str = "user@example.com",
    role_names: list[str] | None = None,
) -> User:
    from sqlalchemy import select

    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=_hash("SecurePass1!"),
        is_active=True,
        is_superuser=False,
        is_verified=True,
        full_name="Test User",
    )
    session.add(user)
    await session.flush()

    if role_names:
        roles = (
            (await session.execute(select(Role).where(Role.name.in_(role_names)))).scalars().all()
        )
        for role in roles:
            session.add(UserRole(user_id=user.id, role_id=role.id))

    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Public auth pages
# ---------------------------------------------------------------------------


class TestLoginPage:
    @pytest.mark.anyio
    async def test_login_returns_200(self, anon_client):
        resp = await anon_client.get("/users/login")
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_login_response_contains_inertia_component(self, anon_client):
        resp = await anon_client.get(
            "/users/login",
            headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["component"] == "Users/Login"


class TestRegisterPage:
    @pytest.mark.anyio
    async def test_register_disabled_by_default_returns_404(self, anon_client):
        """With allow_signup=False (default), /users/register should 404."""
        resp = await anon_client.get("/users/register")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_register_enabled_returns_200(self, anon_client_signup):
        """With allow_signup=True, /users/register should render."""
        resp = await anon_client_signup.get("/users/register")
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_register_enabled_contains_inertia_component(self, anon_client_signup):
        resp = await anon_client_signup.get(
            "/users/register",
            headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["component"] == "Users/Register"


class TestOtherPublicPages:
    @pytest.mark.anyio
    async def test_forgot_password_returns_200(self, anon_client):
        resp = await anon_client.get("/users/forgot-password")
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_reset_password_returns_200(self, anon_client):
        resp = await anon_client.get("/users/reset-password?token=abc123")
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_verify_returns_200(self, anon_client):
        resp = await anon_client.get("/users/verify?token=tok")
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_accept_invite_returns_200(self, anon_client):
        resp = await anon_client.get("/users/invite/accept?token=tok")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Admin pages
# ---------------------------------------------------------------------------


class TestAdminIndexPage:
    @pytest.mark.anyio
    async def test_admin_without_auth_is_redirected(self, anon_client):
        """Unauthenticated access to the admin page redirects to /users/login."""
        resp = await anon_client.get("/users/admin", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"].endswith("/users/login")

    @pytest.mark.anyio
    async def test_admin_with_admin_session_returns_200(self, admin_client):
        resp = await admin_client.get("/users/admin")
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_admin_inertia_component_is_users_index(self, admin_client):
        resp = await admin_client.get(
            "/users/admin",
            headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["component"] == "Users/Users/Index"


class TestAdminEditPage:
    @pytest.mark.anyio
    async def test_invalid_uuid_returns_404(self, admin_client):
        resp = await admin_client.get("/users/admin/not-a-uuid")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_unknown_uuid_returns_404(self, admin_client):
        missing_id = str(uuid.uuid4())
        resp = await admin_client.get(f"/users/admin/{missing_id}")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_existing_user_returns_200(self, admin_client, users_db):
        user = await _make_verified_user(users_db, email="edit_target@example.com")
        resp = await admin_client.get(f"/users/admin/{user.id}")
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_existing_user_inertia_component(self, admin_client, users_db):
        user = await _make_verified_user(users_db, email="edit_target2@example.com")
        resp = await admin_client.get(
            f"/users/admin/{user.id}",
            headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["component"] == "Users/Users/Edit"


@pytest.mark.anyio
async def test_admin_edit_page_unknown_user_returns_404(admin_client):
    import uuid

    resp = await admin_client.get(
        f"/users/admin/{uuid.uuid4()}",
        follow_redirects=False,
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_roles_payload_returns_id_name_dicts(users_app):
    """Helper reads the roles cache and returns id/name dicts in cache order."""
    from users.endpoints.views import _roles_payload

    payload = await _roles_payload(users_app)

    assert isinstance(payload, list)
    assert all(set(item.keys()) == {"id", "name"} for item in payload)
    names = [item["name"] for item in payload]
    assert "admin" in names
    assert "user" in names


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
