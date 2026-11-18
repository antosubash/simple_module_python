"""Per-message reply addresses survive transports and durable delivery (#1025)."""

import json
from dataclasses import dataclass

import pytest
from simple_module_core import mail
from simple_module_core.durable_events import deserialize_event, serialize_event
from simple_module_core.events import Event


@dataclass
class BookingConfirmed(Event):
    message: mail.MailMessage


@pytest.mark.parametrize(
    "address",
    [
        "",
        "not-an-address",
        "guide@",
        "guide@bad domain",
        "guide@example.com, other@example.com",
        "guide@example.com; other@example.com",
        "guide@example.com\r\nBcc: other@example.com",
        "guide@example.com\rBcc: other@example.com",
        "guide@example.com\nBcc: other@example.com",
        "guide@example.com\x00",
    ],
)
def test_reply_to_rejects_invalid_addresses_and_header_injection(address) -> None:
    with pytest.raises(ValueError, match="reply_to"):
        mail.MailMessage("visitor@example.com", "Booking", "Confirmed", reply_to=address)


@pytest.mark.parametrize("reply_to", [None, "guide@example.com", "guide@localhost"])
def test_reply_to_survives_durable_json_round_trip(reply_to) -> None:
    event = BookingConfirmed(
        mail.MailMessage("visitor@example.com", "Booking", "Confirmed", reply_to=reply_to)
    )
    payload = json.loads(json.dumps(serialize_event(event)))
    assert payload["message"]["reply_to"] == reply_to
    restored = deserialize_event(BookingConfirmed, payload)
    assert restored.message.reply_to == reply_to


async def test_old_payload_without_reply_to_still_sends(captured_mail) -> None:
    event = deserialize_event(
        BookingConfirmed,
        {"message": {"to": "visitor@example.com", "subject": "Booking", "text": "Confirmed"}},
    )
    await (await mail.resolve_mail_sender(object())).send(event.message)
    assert captured_mail.to("visitor@example.com")[0].reply_to is None


def test_durable_payload_rejects_reply_to_header_injection() -> None:
    with pytest.raises(ValueError, match="reply_to"):
        deserialize_event(
            BookingConfirmed,
            {
                "message": {
                    "to": "visitor@example.com",
                    "subject": "Booking",
                    "text": "Confirmed",
                    "reply_to": "guide@example.com\r\nBcc: other@example.com",
                }
            },
        )


async def test_captured_mail_exposes_reply_to(captured_mail) -> None:
    await mail.current_mail_sender().send(
        mail.MailMessage(
            "visitor@example.com", "Booking", "Confirmed", reply_to="guide@example.com"
        )
    )
    assert captured_mail.messages[0].reply_to == "guide@example.com"
    assert captured_mail.to("visitor@example.com")[0].reply_to == "guide@example.com"


@pytest.mark.parametrize("transport", ["console", "console-without-body", "fallback"])
async def test_logging_transports_include_reply_to(caplog, transport) -> None:
    mail.reset_mail_sender()
    sender = (
        mail.current_mail_sender()
        if transport == "fallback"
        else mail.ConsoleMailSender(include_body=transport == "console")
    )
    with caplog.at_level("INFO", logger="simple_module.mail"):
        await sender.send(
            mail.MailMessage(
                "visitor@example.com", "Booking", "secret-token", reply_to="guide@example.com"
            )
        )
    assert "guide@example.com" in caplog.text
    assert caplog.records[-1].mail_reply_to == "guide@example.com"
    if transport != "console":
        assert "secret-token" not in caplog.text
