"""``users.require_verification`` decides whether a signup can sign in at once (GH #547).

The setting was never read: every self-registered account was sent a
verification email and refused at login until verified, so an install with no
SMTP had signups nobody could use.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from _users_oauth_support import find_user, set_users_settings

_EMAIL = "signup@example.com"
_PASSWORD = "SecurePass1!"
_INERTIA_HEADERS = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}


def _configure(app, *, require_verification: bool) -> AsyncMock:
    set_users_settings(app, require_verification=require_verification)
    users = app.state.users
    users.mailer.send_verification = AsyncMock()
    return users.mailer.send_verification


async def _register_then_login(client):
    reg = await client.post(
        "/api/users/auth/register", json={"email": _EMAIL, "password": _PASSWORD}
    )
    assert reg.status_code == 201, reg.text
    return await client.post(
        "/api/users/auth/login", data={"username": _EMAIL, "password": _PASSWORD}
    )


@pytest.mark.anyio
async def test_required_sends_the_email_and_refuses_login(users_app_signup, anon_client_signup):
    sent = _configure(users_app_signup, require_verification=True)

    login = await _register_then_login(anon_client_signup)

    assert login.status_code == 400
    assert login.json()["detail"] == "LOGIN_USER_NOT_VERIFIED"
    sent.assert_awaited_once()
    assert (await find_user(users_app_signup, _EMAIL)).is_verified is False


@pytest.mark.anyio
async def test_not_required_allows_login_without_verifying(users_app_signup, anon_client_signup):
    sent = _configure(users_app_signup, require_verification=False)

    login = await _register_then_login(anon_client_signup)

    assert login.status_code == 204, login.text
    sent.assert_not_awaited()
    # Nobody proved the address, so the account must not claim it was: an SSO
    # sign-in for this email would otherwise link to it.
    assert (await find_user(users_app_signup, _EMAIL)).is_verified is False


@pytest.mark.anyio
async def test_turning_it_off_lets_earlier_signups_in(users_app_signup, anon_client_signup):
    _configure(users_app_signup, require_verification=True)
    assert (await _register_then_login(anon_client_signup)).status_code == 400

    _configure(users_app_signup, require_verification=False)
    login = await anon_client_signup.post(
        "/api/users/auth/login", data={"username": _EMAIL, "password": _PASSWORD}
    )

    assert login.status_code == 204, login.text


@pytest.mark.anyio
@pytest.mark.parametrize("required", [True, False])
async def test_register_page_receives_the_setting(users_app_signup, anon_client_signup, required):
    _configure(users_app_signup, require_verification=required)

    resp = await anon_client_signup.get("/users/register", headers=_INERTIA_HEADERS)

    assert resp.status_code == 200, resp.text
    assert resp.json()["props"]["require_verification"] is required
