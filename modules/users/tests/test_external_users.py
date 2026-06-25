"""External (SSO) user behaviour: null password, marking, and guards.

Covers the feature added on top of the OAuth/OIDC login flow:
- a *new* OAuth login provisions an external user (null password, marked),
- an OAuth login that *links* to an existing password account leaves it local,
- external users cannot password-login or be sent a reset link,
- admins can still assign roles to external users like any other user,
- the admin list surfaces ``is_external``.
"""

from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from users.models import Role, User

_pw = PasswordHelper()


# ---------------------------------------------------------------------------
# Fake OAuth provider (no network) to drive the /login + /callback flow
# ---------------------------------------------------------------------------


class _FakeOAuthClient:
    def __init__(self, account_id: str, account_email: str) -> None:
        self._account_id = account_id
        self._account_email = account_email

    async def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        return f"https://idp.example/authorize?state={state}"

    async def get_access_token(self, code: str, redirect_uri: str) -> dict:
        return {"access_token": "fake-token", "expires_at": None, "refresh_token": None}

    async def get_id_email(self, access_token: str) -> tuple[str, str]:
        return self._account_id, self._account_email


def _install_fake_provider(app, account_id: str, account_email: str) -> None:
    from users.oauth import OAuthProvider

    app.state.users.oauth_clients["microsoft"] = OAuthProvider(
        "microsoft", "Microsoft", _FakeOAuthClient(account_id, account_email)
    )


async def _run_oauth_login(client) -> int:
    """Drive /login then /callback; return the callback status code."""
    login = await client.get("/api/users/auth/microsoft/login", follow_redirects=False)
    assert login.status_code == 302
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    cb = await client.get(
        f"/api/users/auth/microsoft/callback?code=abc&state={state}",
        follow_redirects=False,
    )
    return cb.status_code


async def _get_user_by_email(db, email: str) -> User:
    return (await db.execute(select(User).where(User.email == email))).scalar_one()


# ---------------------------------------------------------------------------
# Provisioning
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_new_oauth_login_creates_external_user(users_app, anon_client, users_db):
    _install_fake_provider(users_app, "ms-oid-1", "sso-new@example.com")

    assert await _run_oauth_login(anon_client) == 303

    user = await _get_user_by_email(users_db, "sso-new@example.com")
    assert user.is_external is True
    assert user.hashed_password is None
    assert user.is_verified is True


@pytest.mark.anyio
async def test_oauth_login_links_existing_password_user_stays_local(
    users_app, anon_client, users_db
):
    existing = User(
        id=uuid.uuid4(),
        email="local@example.com",
        hashed_password=_pw.hash("SecurePass1!"),
        is_active=True,
        is_verified=True,
    )
    users_db.add(existing)
    await users_db.commit()

    _install_fake_provider(users_app, "ms-oid-2", "local@example.com")
    assert await _run_oauth_login(anon_client) == 303

    user = await _get_user_by_email(users_db, "local@example.com")
    assert user.is_external is False
    assert user.hashed_password is not None  # password retained


# ---------------------------------------------------------------------------
# Credential guards
# ---------------------------------------------------------------------------


async def _seed_external_user(db, email: str = "ext@example.com") -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=None,
        is_active=True,
        is_verified=True,
        is_external=True,
    )
    db.add(user)
    await db.commit()
    return user


@pytest.mark.anyio
async def test_external_user_cannot_password_login(users_app, anon_client, users_db):
    await _seed_external_user(users_db, "ext-login@example.com")

    resp = await anon_client.post(
        "/api/users/auth/login",
        data={"username": "ext-login@example.com", "password": "anything-at-all"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "LOGIN_BAD_CREDENTIALS"


@pytest.mark.anyio
async def test_external_user_cannot_bearer_token_login(users_app, anon_client, users_db):
    """The bearer-token login path must reject external users cleanly (401),
    not 500 on a None-hash verify, and without a timing/error enumeration leak."""
    await _seed_external_user(users_db, "ext-token@example.com")

    resp = await anon_client.post(
        "/api/users/auth/token",
        json={"email": "ext-token@example.com", "password": "anything-at-all"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


@pytest.mark.anyio
async def test_admin_reset_link_rejected_for_external_user(admin_client, users_db):
    user = await _seed_external_user(users_db, "ext-reset@example.com")

    resp = await admin_client.post(f"/api/users/admin/{user.id}/reset-password-link")
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_forgot_password_is_noop_for_external_user(users_app):
    from users.db_adapter import UserDatabaseWithRoles
    from users.manager import UserManager
    from users.models import OAuthAccount

    async with users_app.state.sm.db.session_factory() as session:
        user_db = UserDatabaseWithRoles(session, User, OAuthAccount)
        manager = UserManager(user_db, users_app.state.users.mailer, users_app.state.users.settings)

        sent: list[str] = []

        async def _spy(user, token, request=None):
            sent.append(user.email)

        manager.on_after_forgot_password = _spy

        external = User(
            id=uuid.uuid4(),
            email="ext-forgot@example.com",
            hashed_password=None,
            is_active=True,
            is_verified=True,
            is_external=True,
        )
        local = User(
            id=uuid.uuid4(),
            email="local-forgot@example.com",
            hashed_password=_pw.hash("SecurePass1!"),
            is_active=True,
            is_verified=True,
        )

        await manager.forgot_password(external)
        assert sent == []  # SSO account: no reset email

        await manager.forgot_password(local)
        assert sent == ["local-forgot@example.com"]  # control: local account still works


# ---------------------------------------------------------------------------
# Roles + admin visibility (external users are managed like normal users)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_admin_can_assign_role_to_external_user(admin_client, users_db):
    user = await _seed_external_user(users_db, "ext-role@example.com")
    users_db.add(Role(id=uuid.uuid4(), name="member", description="Member"))
    await users_db.commit()

    resp = await admin_client.put(
        f"/api/users/admin/{user.id}/roles",
        json={"role_names": ["member"]},
    )
    assert resp.status_code == 200
    assert "member" in resp.json()["roles"]


@pytest.mark.anyio
async def test_admin_list_exposes_is_external(admin_client, users_db):
    await _seed_external_user(users_db, "ext-list@example.com")

    resp = await admin_client.get("/api/users/admin?per_page=100")
    assert resp.status_code == 200
    rows = {r["email"]: r for r in resp.json()}
    assert rows["ext-list@example.com"]["is_external"] is True
    # The seeded admin is a local account.
    assert rows["admin@example.com"]["is_external"] is False
