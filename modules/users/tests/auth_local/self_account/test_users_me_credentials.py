"""Self-profile routes accept local bearer tokens as well as browser cookies."""

import pytest
from _users_app_builders import user_row


@pytest.mark.parametrize("credential", ["bearer", "cookie"])
async def test_users_me_reads_and_updates_profile(anon_client, alice, users_app, credential):
    if credential == "bearer":
        login = await anon_client.post(
            "/api/users/auth/token",
            json={"email": alice.email, "password": "UserPass1!"},
        )
        assert login.status_code == 200
        anon_client.cookies.clear()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    else:
        login = await anon_client.post(
            "/api/users/auth/login",
            data={"username": alice.email, "password": "UserPass1!"},
        )
        assert login.status_code == 204
        headers = {}

    profile = await anon_client.get("/api/users/me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["id"] == str(alice.id)
    assert profile.json()["email"] == alice.email
    assert "hashed_password" not in profile.json()

    updated = await anon_client.patch(
        "/api/users/me", headers=headers, json={"full_name": "Updated Profile"}
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == str(alice.id)
    assert updated.json()["full_name"] == "Updated Profile"
    assert (await user_row(users_app, alice.email)).full_name == "Updated Profile"


@pytest.mark.parametrize("method", ["GET", "PATCH"])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid-token"}])
async def test_users_me_requires_valid_credentials(anon_client, method, headers):
    response = await anon_client.request(
        method, "/api/users/me", headers=headers, json={"full_name": "Unauthorized"}
    )
    assert response.status_code == 401
