"""Mail metadata travels through the persisted durable outbox (#1006, #1025, #1053)."""

from dataclasses import dataclass

import pytest
from background_tasks.models import OutboxMessage
from background_tasks.outbox.claim import OutboxPolicy
from background_tasks.outbox.dispatch import dispatch
from background_tasks.outbox.transport import WorkerOutboxTransport
from simple_module_core.durable_events import DurableContext
from simple_module_core.events import Event, EventBus
from simple_module_core.mail import MailAttachment, MailMessage, resolve_mail_sender
from sqlmodel import select


@dataclass
class RegistrationConfirmed(Event):
    message: MailMessage


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("legacy_reply_to", [False, True])
@pytest.mark.parametrize("legacy_headers", [False, True])
async def test_outbox_delivers_attachments_and_legacy_payload(
    db_session, db_state, captured_mail, monkeypatch, legacy, legacy_reply_to, legacy_headers
) -> None:
    bus = EventBus()

    async def deliver(event: RegistrationConfirmed, ctx: DurableContext) -> None:
        await (await resolve_mail_sender(ctx.db)).send(event.message)

    bus.subscribe_durable(RegistrationConfirmed, deliver, name="mail-attachment-test")
    transport = WorkerOutboxTransport()
    monkeypatch.setattr(transport, "schedule", lambda db, ids: None)
    bus.durable_transport = transport
    attachments = (
        []
        if legacy
        else [
            MailAttachment(
                filename="invite.ics",
                content_type="text/calendar",
                content=b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
            )
        ]
    )
    await bus.publish_durable(
        RegistrationConfirmed(
            MailMessage(
                "a@test",
                "Confirmation",
                "Body",
                attachments=attachments,
                reply_to="guide@example.com",
                headers={"List-Unsubscribe": "<https://example.com/unsubscribe>"},
            )
        ),
        db_session,
    )
    row = (await db_session.execute(select(OutboxMessage))).scalar_one()
    assert row.payload["message"]["reply_to"] == "guide@example.com"
    assert row.payload["message"]["headers"] == {
        "List-Unsubscribe": "<https://example.com/unsubscribe>"
    }
    if legacy_headers:
        payload = {**row.payload, "message": dict(row.payload["message"])}
        del payload["message"]["headers"]
        row.payload = payload
    if legacy_reply_to:
        payload = {**row.payload, "message": dict(row.payload["message"])}
        del payload["message"]["reply_to"]
        row.payload = payload
    if legacy:
        payload = {**row.payload, "message": dict(row.payload["message"])}
        del payload["message"]["attachments"]
        row.payload = payload
    else:
        assert row.payload["message"]["attachments"][0]["filename"] == "invite.ics"
        assert isinstance(row.payload["message"]["attachments"][0]["content"], str)
    await db_session.commit()
    result = await dispatch(
        db_state.session_factory, bus, OutboxPolicy(max_attempts=8, lease_seconds=300)
    )
    assert result.delivered == 1
    message = captured_mail.to("a@test")[0]
    assert message.subject == "Confirmation"
    assert message.reply_to == (None if legacy_reply_to else "guide@example.com")
    assert message.headers == (
        {} if legacy_headers else {"List-Unsubscribe": "<https://example.com/unsubscribe>"}
    )
    if legacy:
        assert message.attachments == ()
    else:
        assert message.attachments[0].content == b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
