"""Custom mail headers are safe at construction and durable delivery (#1053)."""

import json
from dataclasses import dataclass

import pytest
from simple_module_core.durable_events import deserialize_event, serialize_event
from simple_module_core.events import Event
from simple_module_core.mail import MailMessage


@dataclass
class NewsletterReady(Event):
    message: MailMessage


@pytest.mark.parametrize(
    "name, value",
    [
        (name, "override")
        for name in (
            "From",
            "to",
            "CC",
            "bCc",
            "Subject",
            "Reply-To",
            "Date",
            "Message-ID",
            "Content-Type",
            "content-transfer-encoding",
            "CONTENT-anything",
            "MIME-Version",
        )
    ]
    + [
        ("X-Test\r\nBcc", "a@test"),
        ("X-Test\rBcc", "a@test"),
        ("X-Test\nBcc", "a@test"),
        ("X-Test", "ok\r\nBcc: a@test"),
        ("X-Test", "ok\rBcc: a@test"),
        ("X-Test", "ok\nBcc: a@test"),
        ("", "value"),
        ("X Test", "value"),
        ("X:Test", "value"),
    ],
)
@pytest.mark.parametrize("durable", [False, True])
def test_reserved_or_unsafe_headers_are_rejected(name, value, durable) -> None:
    fields = {"to": "a@test", "subject": "Hi", "text": "Body", "headers": {name: value}}
    with pytest.raises(ValueError, match="header"):
        if durable:
            deserialize_event(NewsletterReady, {"message": fields})
        else:
            MailMessage(**fields)


@pytest.mark.parametrize("legacy", [False, True])
def test_headers_survive_durable_json_and_old_payloads_load(legacy) -> None:
    headers = {"List-Unsubscribe": "<https://example.com/unsubscribe>"}
    event = NewsletterReady(MailMessage("a@test", "Hi", "Body", headers=headers))
    headers.clear()
    payload = json.loads(json.dumps(serialize_event(event)))
    assert payload["message"]["headers"] == {
        "List-Unsubscribe": "<https://example.com/unsubscribe>"
    }
    if legacy:
        del payload["message"]["headers"]
    restored = deserialize_event(NewsletterReady, payload)
    assert restored.message.headers == (
        {} if legacy else {"List-Unsubscribe": "<https://example.com/unsubscribe>"}
    )
