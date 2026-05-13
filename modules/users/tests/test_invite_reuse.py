"""Invite + password-reset token-lifecycle regressions.

The existing ``test_invite_flow`` covers the golden path and rejects a junk
token; these tests add:

* Reusing a verified invite token must be rejected (single-use).
* Generating a reset link for a user produces a token that survives one
  consume cycle and is rejected after the password has been changed (the
  token's hash incorporates ``user.hashed_password``).
* Acceptance for an already-disabled user does not log them in.

If any of these regressed, a stolen invite/reset link could be reused
arbitrarily — exactly the scenario the audit flagged.
"""

from __future__ import annotations

import logging

import pytest


async def _send_invite_and_grab_token(admin_client, anon_client, caplog, email: str) -> str:
    """Issue an invite and pull the token out of the ConsoleMailer log line."""
    with caplog.at_level(logging.INFO, logger="users.mailer"):
        resp = await admin_client.post(
            "/api/users/admin/invite",
            json={"email": email, "role_names": ["user"]},
        )
    assert resp.status_code == 201, resp.text
    records = [r for r in caplog.records if r.getMessage() == "users.invite.email"]
    assert records, "ConsoleMailer didn't log an invite.email record"
    link = records[-1].link  # type: ignore[attr-defined]
    return link.split("token=", 1)[1]


@pytest.mark.anyio
async def test_invite_token_is_single_use(admin_client, anon_client, caplog):
    """Accepting the same invite token twice must fail the second time.

    Verify tokens in fastapi-users flip ``is_verified`` on the user; the
    re-use attempt raises ``UserAlreadyVerified``, which the endpoint maps
    to 400 INVITE_BAD_TOKEN. A regression that re-issued the same JWT or
    forgot to re-check state would let a stolen link be replayed.
    """
    token = await _send_invite_and_grab_token(
        admin_client, anon_client, caplog, "single@example.com"
    )

    first = await anon_client.post(
        "/api/users/auth/accept-invite",
        json={"token": token, "password": "FirstUseSecret1!"},
    )
    assert first.status_code == 204, first.text

    # Same token, same user, but already verified.
    second = await anon_client.post(
        "/api/users/auth/accept-invite",
        json={"token": token, "password": "DifferentSecret2!"},
    )
    assert second.status_code == 400, second.text
    assert second.json()["detail"] == "INVITE_BAD_TOKEN"


@pytest.mark.anyio
async def test_reset_token_invalidated_after_password_change(admin_client, anon_client, caplog):
    """A reset-password token must no longer work once the user's hash changes.

    fastapi-users binds reset tokens to ``user.hashed_password`` so any change
    (including the reset itself, or a manual password update) revokes every
    outstanding reset token. Without this, a leaked link would stay live
    forever.
    """
    # Step 1: create a user via invite, log them in with a known password.
    token = await _send_invite_and_grab_token(
        admin_client, anon_client, caplog, "resetme@example.com"
    )
    await anon_client.post(
        "/api/users/auth/accept-invite",
        json={"token": token, "password": "InitialPass1!"},
    )

    # Step 2: admin mints a reset link.
    listing = await admin_client.get("/api/users/admin")
    target = next(u for u in listing.json() if u["email"] == "resetme@example.com")
    reset = await admin_client.post(f"/api/users/admin/{target['id']}/reset-password-link")
    assert reset.status_code == 200
    reset_token = reset.json()["link"].split("token=", 1)[1]

    # Step 3: user changes password via that token (consumes it).
    used = await anon_client.post(
        "/api/users/auth/reset-password",
        json={"token": reset_token, "password": "PostResetPass1!"},
    )
    assert used.status_code in (200, 204), used.text

    # Step 4: reuse the SAME reset token after password rotated — must fail.
    replay = await anon_client.post(
        "/api/users/auth/reset-password",
        json={"token": reset_token, "password": "ReplayedPass1!"},
    )
    assert replay.status_code in (400, 401), (
        f"Replayed reset token returned {replay.status_code}, expected 4xx. Body: {replay.text!r}"
    )


@pytest.mark.anyio
async def test_disabled_user_cannot_accept_their_invite(admin_client, anon_client, caplog):
    """Inviting + disabling before acceptance must keep the user out."""
    token = await _send_invite_and_grab_token(
        admin_client, anon_client, caplog, "blocked@example.com"
    )

    # Admin disables the freshly-invited user before they accept.
    listing = await admin_client.get("/api/users/admin")
    target = next(u for u in listing.json() if u["email"] == "blocked@example.com")
    disable = await admin_client.patch(f"/api/users/admin/{target['id']}/disable")
    assert disable.status_code == 200
    assert disable.json()["is_active"] is False

    # Token verifies the email but the user is inactive — fastapi-users'
    # subsequent login step (or the session middleware's user-load) must
    # refuse to issue a valid session.
    resp = await anon_client.post(
        "/api/users/auth/accept-invite",
        json={"token": token, "password": "ShouldNotMatter1!"},
    )
    # Either the verify path itself refuses, or the subsequent login does;
    # in both cases the user must not be authenticated afterwards. Probe
    # /me with the post-response cookies to confirm.
    me = await anon_client.get("/api/users/me", follow_redirects=False)
    assert me.status_code in (302, 401), (
        f"Disabled user appears authenticated after accept-invite "
        f"(status={resp.status_code}, /me status={me.status_code})"
    )
