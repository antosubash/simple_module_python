"""Tests for the ConsoleMailer."""

from __future__ import annotations

import logging

import pytest


@pytest.mark.parametrize("url", ["http://localhost:8000", "https://app.example.com"])
@pytest.mark.anyio
async def test_send_verification_logs_link(url, caplog):
    from users.mailer.console import ConsoleMailer

    mailer = ConsoleMailer(base_url=url)
    token = "verify-tok-123"

    with caplog.at_level(logging.INFO, logger="users.mailer"):
        await mailer.send_verification("user@example.com", token)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.getMessage() == "users.verify.email"
    assert record.to == "user@example.com"  # type: ignore[attr-defined]
    expected_link = f"{url.rstrip('/')}/users/verify?token={token}"
    assert record.link == expected_link  # type: ignore[attr-defined]


@pytest.mark.parametrize("url", ["http://localhost:8000", "https://app.example.com"])
@pytest.mark.anyio
async def test_send_password_reset_logs_link(url, caplog):
    from users.mailer.console import ConsoleMailer

    mailer = ConsoleMailer(base_url=url)
    token = "reset-tok-456"

    with caplog.at_level(logging.INFO, logger="users.mailer"):
        await mailer.send_password_reset("user@example.com", token)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.getMessage() == "users.reset.email"
    assert record.to == "user@example.com"  # type: ignore[attr-defined]
    expected_link = f"{url.rstrip('/')}/users/reset-password?token={token}"
    assert record.link == expected_link  # type: ignore[attr-defined]


@pytest.mark.parametrize("url", ["http://localhost:8000", "https://app.example.com"])
@pytest.mark.anyio
async def test_send_invite_logs_link(url, caplog):
    from users.mailer.console import ConsoleMailer

    mailer = ConsoleMailer(base_url=url)
    token = "invite-tok-789"

    with caplog.at_level(logging.INFO, logger="users.mailer"):
        await mailer.send_invite("newuser@example.com", token, "Alice Admin")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.getMessage() == "users.invite.email"
    assert record.to == "newuser@example.com"  # type: ignore[attr-defined]
    expected_link = f"{url.rstrip('/')}/users/invite/accept?token={token}"
    assert record.link == expected_link  # type: ignore[attr-defined]
    assert record.invited_by == "Alice Admin"  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_base_url_trailing_slash_stripped(caplog):
    """ConsoleMailer strips trailing slash from base_url in all links."""
    from users.mailer.console import ConsoleMailer

    mailer = ConsoleMailer(base_url="http://localhost:8000/")

    with caplog.at_level(logging.INFO, logger="users.mailer"):
        await mailer.send_verification("a@b.com", "tok")

    link = caplog.records[0].link  # type: ignore[attr-defined]
    assert not link.startswith("http://localhost:8000//")
    assert link == "http://localhost:8000/users/verify?token=tok"


@pytest.mark.anyio
async def test_console_logs_configured_app_name(caplog):
    """A supplied provider brands the console log; otherwise the default."""
    from users.mailer.console import ConsoleMailer

    branded = ConsoleMailer(base_url="http://localhost:8000", app_name_provider=lambda: "Acme")
    default = ConsoleMailer(base_url="http://localhost:8000")

    with caplog.at_level(logging.INFO, logger="users.mailer"):
        await branded.send_invite("a@b.com", "tok", "Alice")
        await default.send_verification("a@b.com", "tok")

    assert caplog.records[0].app_name == "Acme"  # type: ignore[attr-defined]
    assert caplog.records[1].app_name == "SimpleModule"  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_smtp_emails_carry_the_app_name(monkeypatch):
    """SMTP subjects + bodies include the live app name (and keep the link)."""
    from users.mailer.smtp import SmtpMailer

    captured: list[dict[str, str]] = []

    async def fake_send(self, to: str, subject: str, body: str) -> None:
        captured.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(SmtpMailer, "_send", fake_send)
    mailer = SmtpMailer(
        host="smtp.test",
        port=25,
        username="",
        password="",
        from_address="from@test",
        use_tls=False,
        base_url="http://localhost:8000",
        app_name_provider=lambda: "Acme",
    )

    await mailer.send_invite("new@x.com", "tok", "Alice")
    await mailer.send_verification("v@x.com", "vtok")
    await mailer.send_password_reset("r@x.com", "rtok")

    invite, verify, reset = captured
    assert "Acme" in invite["subject"] and "Alice" in invite["subject"]
    assert "Acme" in invite["body"]
    assert "http://localhost:8000/users/invite/accept?token=tok" in invite["body"]
    assert "Acme" in verify["subject"] and "Acme" in verify["body"]
    assert "Acme" in reset["subject"] and "Acme" in reset["body"]
