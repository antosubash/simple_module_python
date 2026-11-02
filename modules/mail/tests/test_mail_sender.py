"""Settings -> sender selection and the message SmtpMailSender builds."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from mail.sender import SmtpMailSender, build_sender
from mail.settings import MailSettings
from simple_module_core.mail import ConsoleMailSender, MailMessage


def test_defaults() -> None:
    s = MailSettings()
    assert (s.backend, s.smtp_host, s.smtp_port) == ("console", "", 587)
    assert (s.smtp_username, s.smtp_password) == ("", "")
    assert s.smtp_from == "no-reply@localhost"
    assert s.smtp_tls is True


def test_console_backend_builds_a_logging_sender_with_bodies() -> None:
    sender = build_sender(MailSettings())
    assert isinstance(sender, ConsoleMailSender)
    assert sender.include_body is True
    assert sender.delivers_email is False


def test_smtp_backend_builds_an_smtp_sender() -> None:
    sender = build_sender(MailSettings(backend="smtp", smtp_host="smtp.test"))
    assert isinstance(sender, SmtpMailSender)
    assert sender.delivers_email is True


def test_unknown_backend_is_rejected() -> None:
    with pytest.raises(ValueError):
        MailSettings(backend="carrier-pigeon")


def _smtp() -> SmtpMailSender:
    return SmtpMailSender("smtp.test", 2525, "user", "pw", "from@test", True)


async def test_send_builds_a_plain_text_message(monkeypatch) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.sender.aiosmtplib.send", send)

    await _smtp().send(MailMessage(to="to@test", subject="Hi", text="Body"))

    (email,), kwargs = send.call_args
    assert (email["From"], email["To"], email["Subject"]) == ("from@test", "to@test", "Hi")
    assert email.get_content_type() == "text/plain"
    assert email.get_content().strip() == "Body"
    assert kwargs == {
        "hostname": "smtp.test",
        "port": 2525,
        "username": "user",
        "password": "pw",
        "use_tls": True,
        "timeout": 15.0,
    }


async def test_send_adds_an_html_alternative(monkeypatch) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.sender.aiosmtplib.send", send)

    await _smtp().send(MailMessage(to="to@test", subject="Hi", text="Body", html="<b>Body</b>"))

    (email,), _ = send.call_args
    assert email.get_content_type() == "multipart/alternative"
    parts = {p.get_content_type(): p.get_content().strip() for p in email.iter_parts()}
    assert parts == {"text/plain": "Body", "text/html": "<b>Body</b>"}


async def test_blank_credentials_are_sent_as_none(monkeypatch) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.sender.aiosmtplib.send", send)

    sender = SmtpMailSender("h", 25, "", "", "f@test", False)
    await sender.send(MailMessage(to="t@test", subject="s", text="b"))

    _, kwargs = send.call_args
    assert kwargs["username"] is None and kwargs["password"] is None


def test_console_backend_outside_development_does_not_log_bodies() -> None:
    """Reset and invite bodies carry one-time tokens (production console backend)."""
    from mail.sender import build_sender
    from mail.settings import MailSettings

    assert build_sender(MailSettings(), log_bodies=False).include_body is False
    assert build_sender(MailSettings()).include_body is True


@pytest.mark.parametrize("port", [-1, 0, 65536, 99999])
def test_smtp_port_outside_the_tcp_range_is_rejected(port) -> None:
    from mail.settings import MailSettings
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MailSettings(smtp_port=port)
