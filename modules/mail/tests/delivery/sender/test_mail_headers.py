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
        BytesParser(policy=policy.default).parsebytes(call.args[0].as_bytes())
        for call in send.call_args_list
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


async def test_existing_generated_headers_are_preserved(monkeypatch) -> None:
    email = EmailMessage()
    email["Date"] = "Tue, 01 Jan 2030 00:00:00 +0000"
    email["Message-ID"] = "<original@example.org>"
    monkeypatch.setattr("mail.delivery.sender.EmailMessage", lambda: email)
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", AsyncMock())
    await SmtpMailSender("smtp.test", 25, "", "", "sender@example.com", False).send(
        MailMessage("a@test", "Hi", "Body")
    )
    assert email.get_all("Date") == ["Tue, 01 Jan 2030 00:00:00 +0000"]
    assert email.get_all("Message-ID") == ["<original@example.org>"]


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
    email = BytesParser(policy=policy.default).parsebytes(send.call_args.args[0].as_bytes())
    assert email["List-Unsubscribe"] == "<https://example.com/unsubscribe>"
    assert all(part["List-Unsubscribe"] is None for part in list(email.walk())[1:])


@pytest.mark.parametrize(
    "headers", [{"Bcc": "hidden@test"}, {"X-Test": "value\r\nBcc: hidden@test"}]
)
async def test_smtp_rejects_headers_mutated_after_construction(monkeypatch, headers) -> None:
    send = AsyncMock()
    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)
    message = MailMessage("a@test", "Hi", "Body")
    message.headers.update(headers)
    with pytest.raises(ValueError, match="header"):
        await SmtpMailSender("smtp.test", 25, "", "", "sender@example.com", False).send(message)
    send.assert_not_awaited()
