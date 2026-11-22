"""Attachment validation and durable JSON compatibility (#1006)."""

import json
from dataclasses import dataclass
from unittest.mock import Mock

import pytest
from simple_module_core.eventing.durable_events import deserialize_event, serialize_event
from simple_module_core.eventing.events import Event
from simple_module_core.mailer import mail


@dataclass
class Confirmation(Event):
    message: mail.MailMessage


def test_message_accepts_attachment_lists_and_freezes_them() -> None:
    attachment = mail.MailAttachment(
        filename="invite.ics", content_type="text/calendar", content=b""
    )
    items = [attachment]
    message = mail.MailMessage("a@test", "Hi", "Body", attachments=items)
    items.clear()
    assert message.attachments == (attachment,)
    with pytest.raises(ValueError, match="frozen"):
        attachment.content = b"changed after validation"


@pytest.mark.parametrize(
    "filename", ["../a.ics", "dir/a.ics", "dir\\a.ics", "", ".", "..", "a\r\nb", "a\x00b"]
)
def test_invalid_filename_is_rejected(filename) -> None:
    with pytest.raises(ValueError, match="filename"):
        mail.MailAttachment(filename=filename, content_type="text/calendar", content=b"")


@pytest.mark.parametrize(
    "content_type",
    [
        "text",
        "/calendar",
        "text/",
        "text/calendar/extra",
        "text/calendar;method=REQUEST",
        "text/ calendar",
        "text/calendar\r\nX: y",
        "t\u00e9xt/plain",
    ],
)
def test_invalid_content_type_is_rejected(content_type) -> None:
    with pytest.raises(ValueError, match="content_type"):
        mail.MailAttachment(filename="a.ics", content_type=content_type, content=b"")


@pytest.mark.parametrize(
    "content_type", ["text/calendar", "application/vnd.example+json", "application/x-custom"]
)
def test_valid_content_types(content_type) -> None:
    assert (
        mail.MailAttachment(filename="a.ics", content_type=content_type, content=b"").content_type
        == content_type
    )


def test_total_attachment_limit_includes_every_file_and_accepts_boundary() -> None:
    large = mail.MailAttachment(
        filename="a.bin",
        content_type="application/octet-stream",
        content=b"x" * mail.MAX_ATTACHMENT_BYTES,
    )
    mail.MailMessage("a@test", "Hi", "Body", attachments=[large])
    extra = mail.MailAttachment(
        filename="b.bin", content_type="application/octet-stream", content=b"x"
    )
    with pytest.raises(ValueError, match=r"total.*10485760"):
        mail.MailMessage("a@test", "Hi", "Body", attachments=[large, extra])


def test_durable_round_trip_preserves_calendar_and_binary_bytes() -> None:
    event = Confirmation(
        mail.MailMessage(
            "a@test",
            "Hi",
            "Body",
            attachments=[
                mail.MailAttachment(
                    filename="invite.ics",
                    content_type="text/calendar",
                    content=b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
                ),
                mail.MailAttachment(
                    filename="a.bin",
                    content_type="application/octet-stream",
                    content=b"\x00\xff\xfe",
                ),
            ],
        )
    )
    payload = json.loads(json.dumps(serialize_event(event)))
    assert payload["message"]["attachments"][1]["content"] == "AP/+"
    restored = deserialize_event(Confirmation, payload)
    assert restored == event
    assert restored.message.attachments[0].content == b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"


async def test_old_payload_without_attachments_still_sends(captured_mail) -> None:
    event = deserialize_event(
        Confirmation, {"message": {"to": "a@test", "subject": "Hi", "text": "Body"}}
    )
    await (await mail.resolve_mail_sender(object())).send(event.message)
    assert captured_mail.to("a@test")[0].attachments == ()


async def test_captured_mail_exposes_attachment_bytes(captured_mail) -> None:
    attachment = mail.MailAttachment(
        filename="invite.ics", content_type="text/calendar", content=b"calendar"
    )
    await mail.current_mail_sender().send(
        mail.MailMessage("a@test", "Hi", "Body", attachments=[attachment])
    )
    assert captured_mail.messages[0].attachments[0].content == b"calendar"


@pytest.mark.parametrize("fallback", [False, True])
async def test_console_logs_attachment_metadata_without_content(caplog, fallback) -> None:
    attachment = mail.MailAttachment(
        filename="invite.ics", content_type="text/calendar", content=b"SECRET-CONTENT"
    )
    sender = mail.current_mail_sender() if fallback else mail.ConsoleMailSender()
    with caplog.at_level("INFO", logger="simple_module.mail"):
        await sender.send(mail.MailMessage("a@test", "Hi", "Body", attachments=[attachment]))
    assert "invite.ics" in caplog.text
    assert "14 bytes" in caplog.text
    assert "SECRET-CONTENT" not in caplog.text
    assert "SECRET-CONTENT" not in repr([vars(r) for r in caplog.records])


def test_invalid_base64_payload_is_rejected() -> None:
    with pytest.raises(ValueError):
        deserialize_event(
            Confirmation,
            {
                "message": {
                    "to": "a@test",
                    "subject": "Hi",
                    "text": "Body",
                    "attachments": [
                        {"filename": "a.ics", "content_type": "text/calendar", "content": "%%%"}
                    ],
                }
            },
        )


@pytest.mark.parametrize("contents", [["A" * 12], ["YWJj"] * 3])
def test_oversized_encoded_total_is_rejected_before_decoding(monkeypatch, contents) -> None:
    monkeypatch.setattr(mail, "MAX_ATTACHMENT_BYTES", 4)
    decode = Mock(wraps=mail.base64.b64decode)
    monkeypatch.setattr(mail.base64, "b64decode", decode)
    with pytest.raises(ValueError, match="attachment total size"):
        deserialize_event(Confirmation, _payload(contents))
    decode.assert_not_called()


@pytest.mark.parametrize("contents", [["eHh4eA=="], ["eA=="] * 4, ["eHh4", "eA=="]])
def test_encoded_boundary_accounts_for_each_files_padding(monkeypatch, contents) -> None:
    monkeypatch.setattr(mail, "MAX_ATTACHMENT_BYTES", 4)
    decode = Mock(wraps=mail.base64.b64decode)
    monkeypatch.setattr(mail.base64, "b64decode", decode)
    event = deserialize_event(Confirmation, _payload(contents))
    assert b"".join(item.content for item in event.message.attachments) == b"xxxx"
    assert decode.call_count == len(contents)


def _payload(contents):
    return {
        "message": {
            "to": "a@test",
            "subject": "Hi",
            "text": "Body",
            "attachments": [
                {"filename": "a.bin", "content_type": "application/octet-stream", "content": c}
                for c in contents
            ],
        }
    }


@pytest.mark.parametrize("content_type", ["message/rfc822", "MESSAGE/global", "multipart/mixed"])
def test_structured_mime_types_are_rejected(content_type) -> None:
    with pytest.raises(ValueError, match=r"structured MIME types.*not supported"):
        mail.MailAttachment(filename="a.bin", content_type=content_type, content=b"body")
