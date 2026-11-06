"""Tests for the built-in TemplatedMailer."""

from __future__ import annotations

import pytest
from users.mailer.templated import TemplatedMailer


@pytest.mark.parametrize("url", ["http://localhost:8000", "https://app.example.com"])
@pytest.mark.anyio
async def test_send_verification_mails_link(url, captured_mail):
    await TemplatedMailer(base_url=url).send_verification("user@example.com", "verify-tok-123")

    (msg,) = captured_mail.to("user@example.com")
    assert f"{url}/users/verify?token=verify-tok-123" in msg.text


@pytest.mark.parametrize("url", ["http://localhost:8000", "https://app.example.com"])
@pytest.mark.anyio
async def test_send_password_reset_mails_link(url, captured_mail):
    await TemplatedMailer(base_url=url).send_password_reset("user@example.com", "reset-tok-456")

    (msg,) = captured_mail.to("user@example.com")
    assert f"{url}/users/reset-password?token=reset-tok-456" in msg.text


@pytest.mark.parametrize("url", ["http://localhost:8000", "https://app.example.com"])
@pytest.mark.anyio
async def test_send_invite_mails_link(url, captured_mail):
    await TemplatedMailer(base_url=url).send_invite(
        "newuser@example.com", "invite-tok-789", "Alice Admin"
    )

    (msg,) = captured_mail.to("newuser@example.com")
    assert f"{url}/users/invite/accept?token=invite-tok-789" in msg.text
    assert "Alice Admin" in msg.subject


@pytest.mark.anyio
async def test_base_url_trailing_slash_stripped(captured_mail):
    await TemplatedMailer(base_url="http://localhost:8000/").send_verification("a@b.com", "tok")

    text = captured_mail.messages[0].text
    assert "http://localhost:8000//" not in text
    assert "http://localhost:8000/users/verify?token=tok" in text


@pytest.mark.anyio
async def test_emails_carry_the_app_name(captured_mail):
    """Subjects + bodies include the live app name (and keep the link)."""
    mailer = TemplatedMailer(base_url="http://localhost:8000", app_name_provider=lambda: "Acme")

    await mailer.send_invite("new@x.com", "tok", "Alice")
    await mailer.send_verification("v@x.com", "vtok")
    await mailer.send_password_reset("r@x.com", "rtok")

    invite, verify, reset = captured_mail.messages
    assert "Acme" in invite.subject and "Alice" in invite.subject
    assert "Acme" in invite.text
    assert "http://localhost:8000/users/invite/accept?token=tok" in invite.text
    assert "Acme" in verify.subject and "Acme" in verify.text
    assert "Acme" in reset.subject and "Acme" in reset.text


@pytest.mark.anyio
async def test_default_app_name_when_no_provider(captured_mail):
    await TemplatedMailer(base_url="http://localhost:8000").send_verification("a@b.com", "tok")

    assert "SimpleModule" in captured_mail.messages[0].subject
