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
