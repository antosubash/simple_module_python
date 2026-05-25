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

    @pytest.mark.anyio
    async def test_dev_accounts_empty_outside_development(self, anon_client):
        """``dev_accounts`` MUST NOT surface bootstrap creds in non-dev envs."""
        resp = await anon_client.get(
            "/users/login",
            headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
        )
        assert resp.json()["props"]["dev_accounts"] == []

    @pytest.mark.anyio
    async def test_dev_accounts_resolved_via_dotenv_fallback(
        self, anon_client, users_app, monkeypatch
    ):
        """Regression for #159: login_page surfaces creds seeded only via .env.

        With ``environment=development`` and bootstrap vars present only in
        ``.env`` (not on settings, not on ``os.environ``), the buttons must
        still appear — otherwise the admin gets seeded by the boot-time hook
        but the dev-quick-login UX silently breaks.
        """
        from users import bootstrap as bootstrap_module

        monkeypatch.setattr(users_app.state.sm.settings, "environment", "development")
        monkeypatch.setattr(
            bootstrap_module,
            "_read_dotenv_bootstrap_vars",
            lambda: {
                "SM_USERS_BOOTSTRAP_EMAIL": "admin@example.com",
                "SM_USERS_BOOTSTRAP_PASSWORD": "AdminPass1!",
                "SM_USERS_BOOTSTRAP_USER_EMAIL": "user@example.com",
                "SM_USERS_BOOTSTRAP_USER_PASSWORD": "UserPass1!",
            },
        )

        resp = await anon_client.get(
            "/users/login",
            headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
        )

        dev_accounts = resp.json()["props"]["dev_accounts"]
        assert dev_accounts == [
            {"label": "Admin", "email": "admin@example.com", "password": "AdminPass1!"},
            {"label": "User", "email": "user@example.com", "password": "UserPass1!"},
        ]

    @pytest.mark.anyio
    async def test_login_redirect_url_is_dashboard_when_installed(self, anon_client):
        """Regression for #173: with Dashboard installed, prop stays /dashboard/."""
        resp = await anon_client.get(
            "/users/login",
            headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"},
        )
        assert resp.json()["props"]["login_redirect_url"] == "/dashboard/"


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
    from users.admin.views import _roles_payload

    payload = await _roles_payload(users_app)

    assert isinstance(payload, list)
    assert all(set(item.keys()) == {"id", "name"} for item in payload)
    names = [item["name"] for item in payload]
    assert "admin" in names
    assert "user" in names


@pytest.mark.anyio
async def test_login_redirect_fallback_without_dashboard(users_app):
    """Regression for #173: without Dashboard, redirect falls back to
    the first sibling module view_prefix, not ``/`` (which may 404)."""
    sm = users_app.state.sm
    original = sm.modules
    no_dash = tuple(m for m in original if m.meta.name != "Dashboard")
    assert len(no_dash) < len(original), "test setup: Dashboard should exist"

    settings = users_app.state.users.settings
    settings.login_redirect_url = "/dashboard/"
    object.__setattr__(sm, "modules", no_dash)
    try:
        from users.module import UsersModule

        mod = UsersModule()
        await mod.on_startup(users_app)
        url = settings.login_redirect_url
        assert url != "/", "must not fall back to / (may 404)"
        assert url.startswith("/"), "must be an absolute path"
        assert url.endswith("/"), "must have trailing slash"
    finally:
        object.__setattr__(sm, "modules", original)
