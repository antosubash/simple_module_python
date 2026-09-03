"""Props and cookie behaviour behind the public auth screens.

The hi-fi deck's sign-in / reset / verify / invite cards say concrete things —
"valid for 60 minutes", "Keep me signed in for 30 days", "Link expired",
"in 5 days" — and every one of those is a fact the server owns. These tests
pin the server side of that copy: the numbers come from settings, the dead-link
states are decided on GET rather than after a failed submit, and remembering a
sign-in actually lengthens the credential.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi_users.jwt import generate_jwt
from fastapi_users.password import PasswordHelper
from users.models import User

_pw = PasswordHelper()

_INERTIA_HEADERS = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}
_RESET_SECRET = "test-reset-secret-32-bytes-xxxxx"
_VERIFY_SECRET = "test-verify-secret-32-bytes-xxxxx"
_RESET_AUDIENCE = "fastapi-users:reset"
_VERIFY_AUDIENCE = "fastapi-users:verify"

REMEMBER_ME_MAX_AGE = 30 * 24 * 60 * 60


async def _make_user(session, email: str, password: str = "SecurePass1!") -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=_pw.hash(password),
        is_active=True,
        is_superuser=False,
        is_verified=True,
        full_name="Test User",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _set_cookie(resp, name: str) -> str:
    """Return the raw ``Set-Cookie`` header for *name* (httpx drops attributes)."""
    headers = [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"]
    matching = [h for h in headers if h.startswith(f"{name}=")]
    assert matching, f"no Set-Cookie for {name!r} in {headers!r}"
    return matching[-1]


def _props(resp) -> dict:
    assert resp.status_code == 200, resp.text
    return resp.json()["props"]


# ---------------------------------------------------------------------------
# "Keep me signed in for 30 days"
# ---------------------------------------------------------------------------


class TestRememberMe:
    @pytest.mark.anyio
    async def test_remember_extends_the_auth_cookie_to_thirty_days(self, anon_client, users_db):
        await _make_user(users_db, "remember@example.com")
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={
                "username": "remember@example.com",
                "password": "SecurePass1!",
                "remember": "true",
            },
        )
        assert resp.status_code == 204, resp.text
        assert f"Max-Age={REMEMBER_ME_MAX_AGE}" in _set_cookie(resp, "sm_auth")

    @pytest.mark.anyio
    async def test_without_remember_the_cookie_keeps_the_configured_default(
        self, anon_client, users_db, users_app
    ):
        await _make_user(users_db, "plain@example.com")
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "plain@example.com", "password": "SecurePass1!"},
        )
        assert resp.status_code == 204, resp.text
        default = users_app.state.users.settings.cookie_max_age_seconds
        assert f"Max-Age={default}" in _set_cookie(resp, "sm_auth")

    @pytest.mark.anyio
    async def test_login_page_passes_the_remember_window_in_days(self, anon_client):
        props = _props(await anon_client.get("/users/login", headers=_INERTIA_HEADERS))
        assert props["remember_me_days"] == 30


# ---------------------------------------------------------------------------
# Forgot password — "valid for {minutes} minutes" + the console-mailer callout
# ---------------------------------------------------------------------------


class TestForgotPasswordProps:
    @pytest.mark.anyio
    async def test_lifetime_is_reported_in_minutes(self, anon_client):
        props = _props(await anon_client.get("/users/forgot-password", headers=_INERTIA_HEADERS))
        assert props["reset_link_lifetime_minutes"] == 60

    @pytest.mark.anyio
    async def test_console_mailer_does_not_deliver(self, anon_client):
        """The test app runs the ConsoleMailer, so the amber callout must show."""
        props = _props(await anon_client.get("/users/forgot-password", headers=_INERTIA_HEADERS))
        assert props["mailer_delivers"] is False


# ---------------------------------------------------------------------------
# Reset password — the expired card is decided on GET
# ---------------------------------------------------------------------------


def _reset_token(user_id: uuid.UUID, *, lifetime_seconds: int) -> str:
    return generate_jwt(
        {"sub": str(user_id), "password_fgpt": "x", "aud": _RESET_AUDIENCE},
        _RESET_SECRET,
        lifetime_seconds,
    )


class TestResetPasswordProps:
    @pytest.mark.anyio
    async def test_expired_token_renders_the_expired_card(self, anon_client, users_db):
        user = await _make_user(users_db, "expired-reset@example.com")
        token = _reset_token(user.id, lifetime_seconds=-60)
        props = _props(
            await anon_client.get(f"/users/reset-password?token={token}", headers=_INERTIA_HEADERS)
        )
        assert props["expired"] is True
        assert props["email"] is None

    @pytest.mark.anyio
    async def test_live_token_carries_the_address_to_sign_in_with(self, anon_client, users_db):
        user = await _make_user(users_db, "live-reset@example.com")
        token = _reset_token(user.id, lifetime_seconds=3600)
        props = _props(
            await anon_client.get(f"/users/reset-password?token={token}", headers=_INERTIA_HEADERS)
        )
        assert props["expired"] is False
        assert props["email"] == "live-reset@example.com"

    @pytest.mark.anyio
    async def test_without_a_token_the_page_is_not_expired(self, anon_client):
        """ "No token at all" keeps its own message — "use the link from your
        email" — rather than being reported as a link that ran out."""
        props = _props(await anon_client.get("/users/reset-password", headers=_INERTIA_HEADERS))
        assert props["expired"] is False
        assert props["token"] == ""

    @pytest.mark.anyio
    async def test_lifetime_minutes_reach_the_expired_copy(self, anon_client):
        props = _props(
            await anon_client.get("/users/reset-password?token=nonsense", headers=_INERTIA_HEADERS)
        )
        assert props["reset_link_lifetime_minutes"] == 60


# ---------------------------------------------------------------------------
# Verify email — resend needs the address off a token that is already dead
# ---------------------------------------------------------------------------


class TestVerifyEmailProps:
    @pytest.mark.anyio
    async def test_expired_token_still_yields_the_address(self, anon_client):
        token = generate_jwt(
            {
                "sub": str(uuid.uuid4()),
                "email": "stale@example.com",
                "aud": _VERIFY_AUDIENCE,
            },
            _VERIFY_SECRET,
            -60,
        )
        props = _props(
            await anon_client.get(f"/users/verify?token={token}", headers=_INERTIA_HEADERS)
        )
        assert props["email"] == "stale@example.com"

    @pytest.mark.anyio
    async def test_unreadable_token_leaves_the_address_absent(self, anon_client):
        props = _props(
            await anon_client.get("/users/verify?token=nonsense", headers=_INERTIA_HEADERS)
        )
        assert props["email"] is None

    @pytest.mark.anyio
    async def test_lifetime_is_reported_in_hours(self, anon_client):
        props = _props(await anon_client.get("/users/verify?token=x", headers=_INERTIA_HEADERS))
        assert props["verification_lifetime_hours"] == 24 * 7


# ---------------------------------------------------------------------------
# Accept invite — who invited you, and when the link dies
# ---------------------------------------------------------------------------


class TestInvitePreviewProps:
    @pytest.mark.anyio
    async def test_inviter_and_expiry_surface_when_the_claims_are_present(
        self, anon_client, users_db
    ):
        user = await _make_user(users_db, "invitee@example.com")
        token = generate_jwt(
            {
                "sub": str(user.id),
                "email": user.email,
                "aud": _VERIFY_AUDIENCE,
                "invited_by": "Dana Scully",
            },
            _VERIFY_SECRET,
            3600,
        )
        props = _props(
            await anon_client.get(f"/users/invite/accept?token={token}", headers=_INERTIA_HEADERS)
        )
        invite = props["invite"]
        assert invite["invited_by_name"] == "Dana Scully"
        expires_at = datetime.fromisoformat(invite["expires_at"])
        assert expires_at > datetime.now(UTC)

    @pytest.mark.anyio
    async def test_a_token_minted_without_the_claim_is_tolerated(self, anon_client, users_db):
        user = await _make_user(users_db, "no-inviter@example.com")
        token = generate_jwt(
            {"sub": str(user.id), "email": user.email, "aud": _VERIFY_AUDIENCE},
            _VERIFY_SECRET,
            3600,
        )
        props = _props(
            await anon_client.get(f"/users/invite/accept?token={token}", headers=_INERTIA_HEADERS)
        )
        assert props["invite"]["invited_by_name"] is None
        assert props["invite"]["expires_at"] is not None

    @pytest.mark.anyio
    async def test_an_unreadable_token_previews_nothing(self, anon_client):
        """The dead-link card, not a password form that cannot be accepted."""
        props = _props(
            await anon_client.get("/users/invite/accept?token=tok", headers=_INERTIA_HEADERS)
        )
        assert props["invite"] is None


class TestAcceptInviteFullName:
    @pytest.mark.anyio
    async def test_full_name_from_the_form_is_stored(self, anon_client, users_db, users_app):
        from sqlalchemy import select

        user = User(
            id=uuid.uuid4(),
            email="joins@example.com",
            hashed_password=_pw.hash("Placeholder1!"),
            is_active=True,
            is_verified=False,
        )
        users_db.add(user)
        await users_db.commit()

        token = generate_jwt(
            {"sub": str(user.id), "email": user.email, "aud": _VERIFY_AUDIENCE},
            _VERIFY_SECRET,
            3600,
        )
        resp = await anon_client.post(
            "/api/users/auth/accept-invite",
            json={"token": token, "password": "FreshSecure1!", "full_name": "Rob Meyer"},
        )
        assert resp.status_code == 204, resp.text

        async with users_app.state.sm.db.session_factory() as session:
            stored = (
                await session.execute(select(User).where(User.email == "joins@example.com"))
            ).scalar_one()
        assert stored.full_name == "Rob Meyer"
