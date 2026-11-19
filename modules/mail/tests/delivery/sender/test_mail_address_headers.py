"""SMTP wire headers and envelopes preserve mailbox syntax and IDN domains."""

from email import policy
from email.parser import BytesParser
from unittest.mock import AsyncMock

import aiosmtplib
import pytest
from mail.delivery.sender import SmtpMailSender
from simple_module_core.mail import MailMessage


@pytest.mark.parametrize(
    "to, reply_to, from_address, expected_to, expected_reply, expected_from, display_name",
    [
        (
            "visitor@example.com",
            "guide@bücher.de",
            "platform@example.com",
            ["visitor@example.com"],
            "guide@xn--bcher-kva.de",
            "platform@example.com",
            "",
        ),
        (
            "Visitor <visitor@bücher.de>",
            r'"Jane \"JJ\", Doe" <guide@bücher.de>',
            "Platform <platform@bücher.de>",
            ["visitor@xn--bcher-kva.de"],
            "guide@xn--bcher-kva.de",
            "platform@xn--bcher-kva.de",
            'Jane "JJ", Doe',
        ),
        (
            "Visitors: First <first@bücher.de>, second@example.com;",
            "Jäne <guide@bücher.de>",
            "platform@example.com",
            ["first@xn--bcher-kva.de", "second@example.com"],
            "guide@xn--bcher-kva.de",
            "platform@example.com",
            "Jäne",
        ),
    ],
)
async def test_idn_domains_are_ascii_in_smtp_headers_and_envelopes(
    monkeypatch,
    to,
    reply_to,
    from_address,
    expected_to,
    expected_reply,
    expected_from,
    display_name,
) -> None:
    smtp = aiosmtplib.SMTP()
    monkeypatch.setattr(smtp, "_ehlo_or_helo_if_needed", AsyncMock())
    sendmail = AsyncMock(return_value=({}, "OK"))
    monkeypatch.setattr(smtp, "sendmail", sendmail)

    async def send(email, **kwargs):
        return await smtp.send_message(email)

    monkeypatch.setattr("mail.delivery.sender.aiosmtplib.send", send)
    sender = SmtpMailSender("smtp.test", 25, "", "", from_address, False)
    await sender.send(MailMessage(to, "Booking", "Confirmed", reply_to=reply_to))

    envelope_from, envelope_to, wire = sendmail.call_args.args
    assert envelope_from == expected_from
    assert envelope_to == expected_to
    assert "SMTPUTF8" not in sendmail.call_args.kwargs["mail_options"]
    email = BytesParser(policy=policy.default).parsebytes(wire)
    for name in ("From", "To", "Reply-To"):
        assert not email[name].defects
        assert all(address.domain.isascii() for address in email[name].addresses)
    assert [address.addr_spec for address in email["To"].addresses] == expected_to
    assert email["From"].addresses[0].addr_spec == expected_from
    assert email["Reply-To"].addresses[0].addr_spec == expected_reply
    assert email["Reply-To"].addresses[0].display_name == display_name
    if to.startswith("Visitors:"):
        assert email["To"].groups[0].display_name == "Visitors"
