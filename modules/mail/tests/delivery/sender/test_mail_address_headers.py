"""SMTP wire headers and envelopes preserve mailbox syntax and IDN domains."""

from email import policy
from email.parser import BytesParser, Parser
from unittest.mock import AsyncMock

import aiosmtplib
import pytest
from aiosmtplib.response import SMTPResponse
from mail.delivery.sender import SmtpMailSender
from simple_module_core.mail import MailMessage


@pytest.mark.parametrize("supported", [False, True])
@pytest.mark.parametrize(
    "from_address, to", [("jäne@example.com", "a@test"), ("a@test", "jäne@example.com")]
)
async def test_non_ascii_local_parts_require_smtputf8(
    monkeypatch, supported, from_address, to
) -> None:
    smtp = aiosmtplib.SMTP()
    monkeypatch.setattr("aiosmtplib.api.SMTP", lambda **kwargs: smtp)
    monkeypatch.setattr(smtp, "connect", AsyncMock())
    monkeypatch.setattr(smtp, "quit", AsyncMock())
    monkeypatch.setattr(smtp, "_ehlo_or_helo_if_needed", AsyncMock())
    monkeypatch.setattr(
        smtp, "supports_extension", lambda name: supported and name.lower() == "smtputf8"
    )
    mail = AsyncMock()
    monkeypatch.setattr(smtp, "mail", mail)
    monkeypatch.setattr(smtp, "_send_recipients", AsyncMock(return_value={}))
    data = AsyncMock(return_value=SMTPResponse(250, "OK"))
    monkeypatch.setattr(smtp, "data", data)
    sender = SmtpMailSender("smtp.test", 25, "", "", from_address, False)
    message = MailMessage(to, "Grüße", "Body")

    if not supported:
        with pytest.raises(aiosmtplib.SMTPNotSupported, match="SMTPUTF8"):
            await sender.send(message)
        mail.assert_not_awaited()
        data.assert_not_awaited()
        return

    await sender.send(message)
    assert mail.call_args.args[0] == from_address
    assert "SMTPUTF8" in mail.call_args.kwargs["options"]
    assert mail.call_args.kwargs["encoding"] == "utf-8"
    email = Parser(policy=policy.SMTPUTF8).parsestr(data.call_args.args[0].decode("utf-8"))
    assert email["From"].addresses[0].addr_spec == from_address
    assert email["To"].addresses[0].addr_spec == to
    assert email["Subject"] == "Grüße"


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
    monkeypatch.setattr("aiosmtplib.api.SMTP", lambda **kwargs: smtp)
    monkeypatch.setattr(smtp, "connect", AsyncMock())
    monkeypatch.setattr(smtp, "quit", AsyncMock())
    sendmail = AsyncMock(return_value=({}, "OK"))
    monkeypatch.setattr(smtp, "sendmail", sendmail)

    sender = SmtpMailSender("smtp.test", 25, "", "", from_address, False)
    await sender.send(MailMessage(to, "Booking", "Confirmed", reply_to=reply_to))

    envelope_from, envelope_to, wire = sendmail.call_args.args
    assert envelope_from == expected_from
    assert envelope_to == expected_to
    assert "SMTPUTF8" not in sendmail.call_args.kwargs["mail_options"]
    assert wire.isascii()
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
