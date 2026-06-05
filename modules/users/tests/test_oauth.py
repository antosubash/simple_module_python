"""Unit tests for the OAuth/OIDC plumbing.

Provider client construction and the /authorize+/callback ASGI flow are not
covered here because both depend on real httpx-oauth clients that hit the
network (token exchange, profile fetch). Those are best validated in a manual
QA pass against a dev IdP. What this file *does* cover:

- ``build_clients`` / ``build_client_map`` instantiate clients when configured.
- ``OAuthAccount`` persists and FK-cascades on user delete.
- ``UserManager.oauth_callback`` (the find-or-create core fastapi-users helper
  the route delegates to) creates a fresh user + linked OAuthAccount, and
  associates by email when the user already exists.

HTTP dispatcher and live-reload (``SettingsReloaded``) integration tests live
in ``test_oauth_routes.py``.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from users.models import OAuthAccount, User
from users.oauth import build_client_map, build_clients
from users.settings import UsersSettings

_pw = PasswordHelper()


# ---------------------------------------------------------------------------
# Settings → provider list
# ---------------------------------------------------------------------------


def test_microsoft_settings_defaults():
    s = UsersSettings()
    assert s.oauth_microsoft_client_id == ""
    assert s.oauth_microsoft_client_secret == ""
    assert s.oauth_microsoft_tenant == "common"


def test_oauth_fields_carry_group_metadata_for_settings_ui():
    fields = UsersSettings.model_fields
    assert fields["oauth_google_client_id"].json_schema_extra == {"group": "Google OAuth"}
    assert fields["oauth_github_client_id"].json_schema_extra == {"group": "GitHub OAuth"}
    assert fields["oauth_oidc_discovery_url"].json_schema_extra == {"group": "OIDC"}
    assert fields["oauth_microsoft_client_secret"].json_schema_extra == {"group": "Microsoft OAuth"}


# ---------------------------------------------------------------------------
# build_clients (no-network providers only)
# ---------------------------------------------------------------------------


def test_build_clients_includes_microsoft():
    s = UsersSettings(
        oauth_microsoft_client_id="ms-id",
        oauth_microsoft_client_secret="ms-secret",
    )
    providers = build_clients(s)
    assert [p.name for p in providers] == ["microsoft"]
    assert providers[0].display_name == "Microsoft"
    assert providers[0].client.client_id == "ms-id"


def test_build_clients_skips_microsoft_without_secret():
    s = UsersSettings(oauth_microsoft_client_id="ms-id")  # no secret
    assert [p.name for p in build_clients(s)] == []


@pytest.mark.anyio
async def test_microsoft_authorize_url_carries_tenant():
    s = UsersSettings(
        oauth_microsoft_client_id="ms-id",
        oauth_microsoft_client_secret="ms-secret",
        oauth_microsoft_tenant="my-tenant-guid",
    )
    client = build_client_map(s)["microsoft"].client
    url = await client.get_authorization_url("http://testserver/cb", "state123")
    assert "my-tenant-guid" in url


def test_build_client_map_keys_by_name():
    s = UsersSettings(
        oauth_google_client_id="g-id",
        oauth_google_client_secret="g-secret",
        oauth_microsoft_client_id="ms-id",
        oauth_microsoft_client_secret="ms-secret",
    )
    m = build_client_map(s)
    assert set(m) == {"google", "microsoft"}
    assert m["microsoft"].name == "microsoft"


def test_build_clients_google_and_github():
    s = UsersSettings(
        oauth_google_client_id="g-id",
        oauth_google_client_secret="g-secret",
        oauth_github_client_id="gh-id",
        oauth_github_client_secret="gh-secret",
    )
    providers = build_clients(s)
    assert [p.name for p in providers] == ["google", "github"]
    # Sanity-check that the underlying httpx-oauth client carries our id.
    assert providers[0].client.client_id == "g-id"
    assert providers[1].client.client_id == "gh-id"


# ---------------------------------------------------------------------------
# OAuthAccount persistence + cascade
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_oauth_account_round_trip_and_cascade(users_db):
    user = User(
        id=uuid.uuid4(),
        email="oauth-rt@example.com",
        hashed_password=_pw.hash("SecurePass1!"),
        is_active=True,
        is_verified=True,
    )
    users_db.add(user)
    await users_db.commit()

    account = OAuthAccount(
        user_id=user.id,
        oauth_name="google",
        access_token="tok",
        account_id="google-123",
        account_email=user.email,
    )
    users_db.add(account)
    await users_db.commit()

    found = (
        await users_db.execute(select(OAuthAccount).where(OAuthAccount.account_id == "google-123"))
    ).scalar_one()
    assert found.user_id == user.id

    # FK cascade: deleting the user removes the linked account.
    await users_db.delete(user)
    await users_db.commit()
    remaining = (
        await users_db.execute(select(OAuthAccount).where(OAuthAccount.account_id == "google-123"))
    ).scalar_one_or_none()
    assert remaining is None


# ---------------------------------------------------------------------------
# UserManager.oauth_callback — the find-or-create flow the route delegates to
# ---------------------------------------------------------------------------


async def _build_user_manager(app):
    """Construct a UserManager bound to the test app's DB session."""
    from users.db_adapter import UserDatabaseWithRoles
    from users.manager import UserManager
    from users.models import OAuthAccount, User

    session = app.state.sm.db.session_factory()
    s = await session.__aenter__()
    user_db = UserDatabaseWithRoles(s, User, OAuthAccount)
    manager = UserManager(user_db, app.state.users.mailer, app.state.users.settings)
    return manager, session, s


@pytest.mark.anyio
async def test_oauth_callback_creates_new_user_and_account(users_app):
    manager, session, _ = await _build_user_manager(users_app)
    try:
        user = await manager.oauth_callback(
            "google",
            access_token="tok",
            account_id="google-new-1",
            account_email="newuser@example.com",
            associate_by_email=True,
            is_verified_by_default=True,
        )
        assert user.email == "newuser@example.com"
        assert user.is_verified is True
        assert len(user.oauth_accounts) == 1
        assert user.oauth_accounts[0].oauth_name == "google"
        assert user.oauth_accounts[0].account_id == "google-new-1"
    finally:
        await session.__aexit__(None, None, None)


@pytest.mark.anyio
async def test_oauth_callback_links_to_existing_email(users_app, users_db):
    existing = User(
        id=uuid.uuid4(),
        email="existing@example.com",
        hashed_password=_pw.hash("SecurePass1!"),
        is_active=True,
        is_verified=True,
    )
    users_db.add(existing)
    await users_db.commit()

    manager, session, _ = await _build_user_manager(users_app)
    try:
        linked = await manager.oauth_callback(
            "github",
            access_token="tok",
            account_id="gh-42",
            account_email="existing@example.com",
            associate_by_email=True,
            is_verified_by_default=True,
        )
        assert linked.id == existing.id
        names = [a.oauth_name for a in linked.oauth_accounts]
        assert names == ["github"]
    finally:
        await session.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# UsersState defaults
# ---------------------------------------------------------------------------


def test_users_state_defaults_empty_oauth_clients():
    from users.state import UsersState

    state = UsersState(settings=UsersSettings())
    assert state.oauth_clients == {}
