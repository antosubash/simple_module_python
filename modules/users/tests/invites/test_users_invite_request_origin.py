"""Request-based invite links survive the transaction and the resend path."""

import pytest

_ADMIN = "/api/users/admin"


@pytest.mark.parametrize("bulk", [False, True])
async def test_invite_and_resend_use_allowlisted_request_origin(
    admin_client, users_app, captured_mail, bulk
):
    users_app.state.users.settings.base_url = ""
    users_app.state.host.settings.public_base_url = ""
    users_app.state.host.settings.forwarded_host_allowlist = ["app.example"]
    origin = "https://app.example"
    email = "allowlisted@example.com"
    if bulk:
        response = await admin_client.post(
            f"{origin}{_ADMIN}/invite/bulk", json={"emails": [email]}
        )
        assert response.status_code == 200, response.text
        assert response.json()["results"][0]["status"] == "sent"
        users = await admin_client.get(f"{origin}{_ADMIN}", params={"q": email})
        user_id = next(user["id"] for user in users.json() if user["email"] == email)
    else:
        response = await admin_client.post(f"{origin}{_ADMIN}/invite", json={"email": email})
        assert response.status_code == 201, response.text
        user_id = response.json()["id"]

    response = await admin_client.post(f"{origin}{_ADMIN}/{user_id}/resend-invite")
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "sent"
    messages = captured_mail.to(email)
    assert len(messages) == 2
    assert all(f"{origin}/users/invite/accept?token=" in msg.text for msg in messages)
