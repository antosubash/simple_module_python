"""Settings -> sender selection and the message SmtpMailSender builds."""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
from unittest.mock import AsyncMock

import pytest
from mail.core.settings import MailSettings
from mail.delivery.sender import SmtpMailSender, build_sender
from simple_module_core.mailer.mail import ConsoleMailSender, MailAttachment, MailMessage

pytestmark = pytest.mark.usefixtures("smtp_socket")


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
        build_sender(MailSettings(backend="carrier-pigeon"), development=False)


def _smtp() -> SmtpMailSender:
    return SmtpMailSender("smtp.test", 2525, "user", "pw", "from@test", True)


async def test_send_builds_a_plain_text_message(monkeypatch, smtp_socket) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)

    await _smtp().send(MailMessage(to="to@test", subject="Hi", text="Body"))

    (wire,), kwargs = send.call_args
    email = BytesParser(policy=policy.default).parsebytes(wire)
    assert (email["From"], email["To"], email["Subject"]) == ("from@test", "to@test", "Hi")
    assert email.get_content_type() == "text/plain"
    assert email.get_content().strip() == "Body"
    assert kwargs == {
        "sender": "from@test",
        "recipients": ["to@test"],
        "mail_options": [],
        "hostname": "smtp.test",
        "sock": smtp_socket,
        "username": "user",
        "password": "pw",
        "use_tls": False,
        "start_tls": True,
        "timeout": 15.0,
    }


async def test_send_adds_an_html_alternative(monkeypatch) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)

    await _smtp().send(MailMessage(to="to@test", subject="Hi", text="Body", html="<b>Body</b>"))

    email = BytesParser(policy=policy.default).parsebytes(send.call_args.args[0])
    assert email.get_content_type() == "multipart/alternative"
    parts = {p.get_content_type(): p.get_content().strip() for p in email.iter_parts()}
    assert parts == {"text/plain": "Body", "text/html": "<b>Body</b>"}


@pytest.mark.parametrize(
    "reply_to",
    [
        None,
        "guide@example.com",
        "Guide <guide@example.com>",
        '"Doe, Jane" <guide@example.com>',
        r'"Jane \"JJ\", Doe" <guide@example.com>',
    ],
)
async def test_smtp_reply_to_header(monkeypatch, reply_to) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)
    await _smtp().send(MailMessage("to@test", "Booking", "Confirmed", reply_to=reply_to))
    email = BytesParser(policy=policy.default).parsebytes(send.call_args.args[0])
    assert email["Reply-To"] == reply_to
    assert email["From"] == "from@test"
    assert email["To"] == "to@test"


async def test_blank_credentials_are_sent_as_none(monkeypatch) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)

    sender = SmtpMailSender("h", 25, "", "", "f@test", False)
    await sender.send(MailMessage(to="t@test", subject="s", text="b"))

    _, kwargs = send.call_args
    assert kwargs["username"] is None and kwargs["password"] is None


@pytest.mark.parametrize("html", [None, "<b>Body</b>"])
async def test_smtp_attachment_parts_preserve_filename_type_and_bytes(monkeypatch, html) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)
    await _smtp().send(
        MailMessage(
            "to@test",
            "Hi",
            "Body",
            html=html,
            attachments=[
                MailAttachment(
                    filename="invite.ics",
                    content_type="text/calendar",
                    content=b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
                ),
                MailAttachment(
                    filename="r\u00e9sum\u00e9.bin",
                    content_type="application/octet-stream",
                    content=b"\x00\xff",
                ),
            ],
        )
    )
    email = BytesParser(policy=policy.default).parsebytes(send.call_args.args[0])
    parts = list(email.iter_attachments())
    assert [
        (p.get_filename(), p.get_content_type(), p.get_payload(decode=True)) for p in parts
    ] == [
        ("invite.ics", "text/calendar", b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"),
        ("r\u00e9sum\u00e9.bin", "application/octet-stream", b"\x00\xff"),
    ]
    assert all(p.get_content_disposition() == "attachment" for p in parts)
    assert email.get_body(preferencelist=("plain",)).get_content().strip() == "Body"
    if html:
        assert email.get_body(preferencelist=("html",)).get_content().strip() == html


def test_console_backend_outside_development_does_not_log_bodies() -> None:
    """Reset and invite bodies carry one-time tokens (production console backend)."""
    from mail.core.settings import MailSettings
    from mail.delivery.sender import build_sender

    assert build_sender(MailSettings(), log_bodies=False).include_body is False
    assert build_sender(MailSettings()).include_body is True


@pytest.mark.parametrize("port", [-1, 0, 65536, 99999])
def test_smtp_port_outside_the_tcp_range_is_rejected(port) -> None:
    from mail.core.settings import MailSettings
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MailSettings(smtp_port=port)


@pytest.mark.parametrize(
    "port,tls,mode,expected",
    [
        (587, True, "auto", (False, True)),
        (465, True, "auto", (True, False)),
        (1465, True, "implicit", (True, False)),
        (465, True, "starttls", (False, True)),
        (587, False, "auto", (False, False)),
        (465, False, "auto", (False, False)),
        (1465, False, "implicit", (False, False)),
        (465, False, "starttls", (False, False)),
    ],
)
async def test_tls_mode_for_send_and_connection(monkeypatch, port, tls, mode, expected):
    from unittest.mock import MagicMock

    send = AsyncMock()
    client = AsyncMock()
    smtp = MagicMock(return_value=client)
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.SMTP", smtp)
    sender = build_sender(
        MailSettings(
            backend="smtp", smtp_host="smtp.test", smtp_port=port, smtp_tls=tls, smtp_tls_mode=mode
        )
    )
    await sender.send(MailMessage("to@test", "Hi", "Body"))
    await sender.verify_connection()
    for kwargs in [send.call_args.kwargs, smtp.call_args.kwargs]:
        assert (kwargs["use_tls"], kwargs.get("start_tls")) == expected
    client.connect.assert_awaited_once()


def test_unknown_tls_mode_is_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MailSettings(smtp_tls_mode="typo")
