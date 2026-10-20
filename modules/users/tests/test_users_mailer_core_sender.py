"""The users mailer sends through the framework mail sender, looked up per send."""

from __future__ import annotations

import pytest
from simple_module_core.mail import install_mail_sender
from simple_module_test.mail import CapturedMail

_BULK = "/api/users/admin/invite/bulk"


def _invites(captured_mail, address: str):
    """Invite mails only: creating the account also sends a verification mail."""
    return [m for m in captured_mail.to(address) if "invited you" in m.subject]


@pytest.mark.anyio
async def test_invite_sends_one_message_with_link_and_subject(admin_client, captured_mail):
    resp = await admin_client.post(
        "/api/users/admin/invite", json={"email": "inv@example.com", "role_names": []}
    )
    assert resp.status_code == 201, resp.text

    (msg,) = _invites(captured_mail, "inv@example.com")
    assert "/users/invite/accept?token=" in msg.text
    assert msg.subject.endswith("invited you to SimpleModule")


@pytest.mark.anyio
async def test_reset_sends_one_message_with_link_and_subject(users_app, captured_mail):
    await users_app.state.users.mailer.send_password_reset("r@example.com", "rtok")

    (msg,) = captured_mail.to("r@example.com")
    assert "http://testserver/users/reset-password?token=rtok" in msg.text
    assert msg.subject == "Reset your SimpleModule password"


@pytest.mark.anyio
async def test_verification_sends_one_message_with_link_and_subject(users_app, captured_mail):
    await users_app.state.users.mailer.send_verification("v@example.com", "vtok")

    (msg,) = captured_mail.to("v@example.com")
    assert "http://testserver/users/verify?token=vtok" in msg.text
    assert msg.subject == "Verify your email for SimpleModule"


@pytest.mark.anyio
async def test_delivers_email_follows_the_installed_sender(users_app, captured_mail):
    mailer = users_app.state.users.mailer
    assert mailer.delivers_email is True

    install_mail_sender(CapturedMail(delivers_email=False))
    assert mailer.delivers_email is False


@pytest.mark.anyio
async def test_sender_is_resolved_at_send_time(users_app, captured_mail):
    mailer = users_app.state.users.mailer
    later = CapturedMail()
    install_mail_sender(later)

    await mailer.send_verification("late@example.com", "tok")

    assert later.to("late@example.com") and not captured_mail.messages


@pytest.mark.anyio
async def test_non_delivering_sender_makes_resend_return_the_link(admin_client, captured_mail):
    install_mail_sender(CapturedMail(delivers_email=False))
    created = await admin_client.post(
        "/api/users/admin/invite", json={"email": "nd@example.com", "role_names": []}
    )
    resp = await admin_client.post(f"/api/users/admin/{created.json()['id']}/resend-invite")

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "link"
    assert "/users/invite/accept?token=" in (body["link"] or "")


@pytest.mark.anyio
async def test_delivering_sender_makes_resend_mail(admin_client, captured_mail):
    created = await admin_client.post(
        "/api/users/admin/invite", json={"email": "d@example.com", "role_names": []}
    )
    resp = await admin_client.post(f"/api/users/admin/{created.json()['id']}/resend-invite")

    assert resp.json()["status"] == "sent"
    assert len(_invites(captured_mail, "d@example.com")) == 2


@pytest.mark.anyio
async def test_non_delivering_sender_makes_bulk_invite_return_links(admin_client, captured_mail):
    install_mail_sender(CapturedMail(delivers_email=False))
    resp = await admin_client.post(_BULK, json={"emails": ["b1@example.com"], "role_names": []})

    (result,) = resp.json()["results"]
    assert result["status"] == "link"
    assert "/users/invite/accept?token=" in result["link"]
    assert not captured_mail.messages
