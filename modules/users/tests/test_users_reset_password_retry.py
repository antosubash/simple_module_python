"""A password policy rejection must leave a fresh reset token usable (#667)."""

from urllib.parse import parse_qs, urlsplit

import pytest
from _users_app_builders import _make_standard_user


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("short", "Password must be at least 8 characters, not counting spaces"),
        ("12345678", "Password cannot be all numbers"),
    ],
)
async def test_users_reset_rejected_password_allows_same_token_retry(
    admin_client, anon_client, users_app, password, reason
):
    user = await _make_standard_user(users_app)
    link = await admin_client.post(f"/api/users/admin/{user.id}/reset-password-link")
    assert link.status_code == 200, link.text
    token = parse_qs(urlsplit(link.json()["link"]).query)["token"][0]

    rejected = await anon_client.post(
        "/api/users/auth/reset-password", json={"token": token, "password": password}
    )
    assert rejected.status_code == 400, rejected.text
    assert rejected.json()["detail"] == {
        "code": "RESET_PASSWORD_INVALID_PASSWORD",
        "reason": reason,
    }

    accepted = await anon_client.post(
        "/api/users/auth/reset-password", json={"token": token, "password": "CompliantPass1!"}
    )
    assert accepted.status_code == 200, accepted.text
    login = await anon_client.post(
        "/api/users/auth/login", data={"username": user.email, "password": "CompliantPass1!"}
    )
    assert login.status_code == 204, login.text
