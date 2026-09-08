"""Props and cookie behaviour behind the public auth screens.

The hi-fi deck's sign-in / reset / verify / invite cards say concrete things —
"valid for 60 minutes", "Link expired", "in 5 days" — and every one of those is
a fact the server owns. These tests pin the server side of that copy: the
numbers come from settings, and the dead-link states are decided on GET rather
than after a submit that was never going to work.

"Keep me signed in" lives next door in ``test_remember_me.py``.
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


def _props(resp) -> dict:
    assert resp.status_code == 200, resp.text
    return resp.json()["props"]


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


def _reset_token(user: User, *, lifetime_seconds: int, fingerprint: str | None = None) -> str:
    """Mint a reset token the way ``forgot_password`` does.

    ``password_fgpt`` is a hash *of the stored hash*, which is how the token
    stops working once the password changes. Pass *fingerprint* to forge one
    that no longer matches — a link that has already been spent.
    """
    return generate_jwt(
        {
            "sub": str(user.id),
            "password_fgpt": fingerprint or _pw.hash(user.hashed_password),
            "aud": _RESET_AUDIENCE,
        },
        _RESET_SECRET,
        lifetime_seconds,
    )


class TestResetPasswordProps:
    @pytest.mark.anyio
    async def test_expired_token_renders_the_expired_card(self, anon_client, users_db):
        user = await _make_user(users_db, "expired-reset@example.com")
        token = _reset_token(user, lifetime_seconds=-60)
        props = _props(
            await anon_client.get(f"/users/reset-password?token={token}", headers=_INERTIA_HEADERS)
        )
        assert props["expired"] is True
        assert props["email"] is None

    @pytest.mark.anyio
    async def test_live_token_carries_the_address_to_sign_in_with(self, anon_client, users_db):
        user = await _make_user(users_db, "live-reset@example.com")
        token = _reset_token(user, lifetime_seconds=3600)
        props = _props(
            await anon_client.get(f"/users/reset-password?token={token}", headers=_INERTIA_HEADERS)
        )
        assert props["expired"] is False
        assert props["email"] == "live-reset@example.com"

    @pytest.mark.anyio
    async def test_a_spent_link_is_already_dead(self, anon_client, users_db):
        """ "Reset links … work once" has to be true on the page, not only in
        the endpoint: a fingerprint that no longer matches the stored hash
        means the password already changed."""
        user = await _make_user(users_db, "spent-reset@example.com")
        token = _reset_token(user, lifetime_seconds=3600, fingerprint=_pw.hash("something-else"))
        props = _props(
            await anon_client.get(f"/users/reset-password?token={token}", headers=_INERTIA_HEADERS)
        )
        assert props["expired"] is True

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
    async def test_lifetime_is_reported_in_days(self, anon_client):
        props = _props(await anon_client.get("/users/verify?token=x", headers=_INERTIA_HEADERS))
        assert props["verification_lifetime_days"] == 7


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
