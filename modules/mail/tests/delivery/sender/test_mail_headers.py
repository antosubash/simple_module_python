"""SMTP emits required and custom headers on the wire (#1053)."""

from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from unittest.mock import AsyncMock

import pytest
from mail.delivery.sender import SmtpMailSender
from simple_module_core.mail import MailAttachment, MailMessage


@pytest.mark.parametrize(
    "from_address, domain",
    [
        ("sender@example.com", "example.com"),
        ('"Doe, Jane" <sender@example.org>', "example.org"),
        ("Platform <sender@bücher.de>", "xn--bcher-kva.de"),
        ("sender", "fallback.example"),
    ],
)
async def test_smtp_date_and_unique_message_id(monkeypatch, from_address, domain) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)
    monkeypatch.setattr("email.utils.socket.getfqdn", lambda: "fallback.example")
    sender = SmtpMailSender("smtp.test", 25, "", "", from_address, False)
    before = datetime.now(UTC).replace(microsecond=0)
    await sender.send(MailMessage("a@test", "Hi", "Body"))
    await sender.send(MailMessage("a@test", "Hi", "Body"))
    messages = [
        BytesParser(policy=policy.default).parsebytes(call.args[0]) for call in send.call_args_list
    ]
    for message in messages:
        assert message["Date"] is not None
        assert message["Message-ID"] is not None
        assert not message["Date"].defects
        assert not message["Message-ID"].defects
        date = parsedate_to_datetime(message["Date"])
        assert before <= date <= datetime.now(UTC)
        assert date.utcoffset().total_seconds() == 0
        assert message["Message-ID"].startswith("<")
        assert message["Message-ID"].endswith(f"@{domain}>")
    assert messages[0]["Message-ID"] != messages[1]["Message-ID"]


@pytest.mark.parametrize("resent", [False, True])
async def test_smtp_envelope_uses_only_from_and_to(monkeypatch, resent) -> None:
    email = EmailMessage()
    # Exercise the envelope guard even if future code introduces routing headers.
    email["Sender"] = "attacker@example.net"
    email["Cc"] = "copy@example.net"
    email["Bcc"] = "hidden@example.net"
    if resent:
        email["Resent-Date"] = "Tue, 01 Jan 2030 00:00:00 +0000"
        email["Resent-From"] = "attacker@example.net"
        email["Resent-To"] = "redirect@example.net"
    monkeypatch.setattr("mail.delivery.sender.EmailMessage", lambda: email)
    send = AsyncMock()
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)
    await SmtpMailSender("smtp.test", 25, "", "", "Platform <sender@bücher.de>", False).send(
        MailMessage(
            'Readers: "Doe, Jane" <jane@bücher.de>, second@example.com;',
            "Hi",
            "Body",
            reply_to="reply@example.net",
            headers={"List-Unsubscribe": "<https://example.com/unsubscribe>"},
        )
    )
    assert send.call_args.kwargs["sender"] == "sender@xn--bcher-kva.de"
    assert send.call_args.kwargs["recipients"] == ["jane@xn--bcher-kva.de", "second@example.com"]


@pytest.mark.parametrize("attached", [False, True])
async def test_custom_header_delivered_on_outer_message(monkeypatch, attached) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)
    message = MailMessage(
        "a@test",
        "Newsletter",
        "Body",
        html="<p>Body</p>",
        headers={"List-Unsubscribe": "<https://example.com/unsubscribe>"},
        attachments=[MailAttachment(filename="a.txt", content_type="text/plain", content=b"a")]
        if attached
        else [],
    )
    await SmtpMailSender("smtp.test", 25, "", "", "sender@example.com", False).send(message)
    email = BytesParser(policy=policy.default).parsebytes(send.call_args.args[0])
    assert email["List-Unsubscribe"] == "<https://example.com/unsubscribe>"
    assert all(part["List-Unsubscribe"] is None for part in list(email.walk())[1:])


@pytest.mark.parametrize(
    "headers",
    [
        {"Bcc": "hidden@test"},
        {"Resent-To": "attacker@example.net"},
        {"X-Test": "value\r\nBcc: hidden@test"},
    ],
)
async def test_smtp_rejects_headers_mutated_after_construction(monkeypatch, headers) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)
    message = MailMessage("a@test", "Hi", "Body")
    message.headers.update(headers)
    with pytest.raises(ValueError, match="header"):
        await SmtpMailSender("smtp.test", 25, "", "", "sender@example.com", False).send(message)
    send.assert_not_awaited()


@pytest.mark.parametrize("value", ["Grüße " * 100, "a" * 1500])
async def test_long_and_non_ascii_header_values_survive_wire_encoding(monkeypatch, value) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)
    await SmtpMailSender("smtp.test", 25, "", "", "sender@example.com", False).send(
        MailMessage("a@test", "Hi", "Body", headers={"X-Description": value})
    )
    wire = send.call_args.args[0]
    assert all(len(line) <= 998 for line in wire.split(b"\r\n"))
    restored = BytesParser(policy=policy.default).parsebytes(wire)
    assert str(restored["X-Description"]) == value


async def test_long_unsubscribe_url_is_unencoded_on_the_wire(monkeypatch) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)
    value = f"<https://example.com/u?token={'a' * 160}>"
    await SmtpMailSender("smtp.test", 25, "", "", "sender@example.com", False).send(
        MailMessage("a@test", "Grüße", "Grüße", headers={"List-Unsubscribe": value})
    )
    wire = send.call_args.args[0]
    headers = wire.split(b"\r\n\r\n", 1)[0]
    unsubscribe = next(line for line in headers.split(b"\r\n") if line.startswith(b"List-"))
    assert unsubscribe == f"List-Unsubscribe: {value}".encode("ascii")
    assert b"=?" not in unsubscribe
    assert b"Subject: =?utf-8?" in headers
    assert wire.isascii()
    restored = BytesParser(policy=policy.default).parsebytes(wire)
    assert restored["Subject"] == "Grüße"
    assert restored["List-Unsubscribe"] == value
    assert restored.get_content().strip() == "Grüße"
