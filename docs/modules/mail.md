# mail

Outgoing mail for the app. The module owns the transport (SMTP through `aiosmtplib`, or a `console` backend that logs each message) and its settings. Other modules never import it: they send through `simple_module_core.mail`, which works whether or not this module is installed.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Mail` |
| `route_prefix` | *(none)* |
| `view_prefix` | *(none)* |
| `depends_on` | `["Settings"]` |

The module has no tables, routes or pages. It is configured on the generic settings page (**Settings -> Modules -> Mail**).

## Settings

DB-backed (`MailSettings`, package `mail`), hot-reloaded without a restart.

| Field | Default | Notes |
|---|---|---|
| `backend` | `console` | `console` logs the body (development) and attachment metadata; `smtp` delivers |
| `smtp_host` | `""` | |
| `smtp_port` | `587` | |
| `smtp_username` | `""` | blank means no authentication |
| `smtp_password` | `""` | masked in the settings UI |
| `smtp_from` | `no-reply@localhost` | |
| `smtp_tls` | `true` | implicit TLS (`use_tls`) |

Earlier versions kept these under `users` (`users.mailer`, `users.smtp_*`). A data migration renames the stored keys to `mail.backend` and `mail.smtp_*`; an existing `mail.*` row wins, and the downgrade reverses it.

## Sending mail from a module

```python
from simple_module_core.mail import MailMessage, current_mail_sender

sender = current_mail_sender()
await sender.send(MailMessage(to="a@example.com", subject="Hi", text="Plain body"))
```

- `current_mail_sender()` is synchronous and never raises; with nothing installed it returns a console sender that logs only the recipient, subject and attachment metadata (bodies carry one-time tokens).
- `sender.delivers_email` is `False` for console senders, so a screen can show a link instead of promising an inbox.
- Code that may run in the outbox worker (no `app`) uses `await resolve_mail_sender(db)`. The module installs a resolver in `register_event_handlers` before its `app is None` return; it hydrates `MailSettings` from the given session. A worker restricted with `SM_MODULES_ENABLED` must therefore list `Mail` (and any module whose durable handler sends mail, such as `Tenants`); without it the tenants invitation handler raises, so the outbox retries the row (and marks it `dead` after its retries) instead of dropping the email.

### Attachments

Pass a list or tuple of `MailAttachment` SQLModel DTOs. For example, attach an
iCalendar event to a registration confirmation:

```python
from simple_module_core.mail import MailAttachment, MailMessage, current_mail_sender

calendar = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "PRODID:-//Example//Registration//EN\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:registration-123@example.com\r\n"
    "DTSTAMP:20261118T090000Z\r\n"
    "DTSTART:20261201T090000Z\r\n"
    "DTEND:20261201T100000Z\r\n"
    "SUMMARY:Workshop\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
).encode("utf-8")

await current_mail_sender().send(
    MailMessage(
        to="a@example.com",
        subject="Registration confirmed",
        text="Your workshop is booked. The calendar event is attached.",
        attachments=[
            MailAttachment(filename="workshop.ics", content_type="text/calendar", content=calendar)
        ],
    )
)
```

`filename` must be nonempty and cannot contain `/`, `\`, control characters, or
be `.` or `..`. `content_type` must be a MIME `type/subtype` without parameters.
Content is bytes; `MAX_ATTACHMENT_BYTES` in `simple_module_core.mail` caps the
combined raw attachment content at **10 MiB** per message. Invalid metadata or
an oversized total raises `ValueError` at construction. The attachment DTO is
frozen and the message copies its attachments into a tuple.

SMTP sends each file as a MIME attachment, alongside plain text and optional
HTML. Console and fallback senders log each filename and byte count, never
attachment content, even when body logging is enabled.

For durable delivery, put the message in a dataclass domain event and publish
with `bus.publish_durable(event, db)` in the transaction. The existing outbox
serializer encodes attachment bytes as base64 in JSON and restores them before
the handler runs. Payloads without `attachments` default to an empty tuple.
The handler sends through `await resolve_mail_sender(ctx.db)` and must not
commit `ctx.db`. Tenant invitations already use durable domain events, building
their message inside the handler; this flow stays unchanged. See
[durable delivery](/framework/events#durable-delivery) for registration and retries.
Base64 adds roughly one third to stored attachment size; outbox payloads contain
the file content, so keep sensitive files under the same access controls as
other queued event data.

## Lifecycle

| Hook | What it does |
|---|---|
| `register_settings` | `register_module_settings` mounts `app.state.mail` |
| `register_health_checks` | adds the on-demand `mail.mailer` check |
| `register_event_handlers` | installs the resolver; on `SettingsReloaded(package="mail")` rebuilds and reinstalls the sender |
| `on_startup` | installs the sender built from the hydrated settings |
| `on_shutdown` | uninstalls the sender and the resolver |

## Health check

`mail.mailer` (`probe=False`, so it never runs on a readiness timer) re-reads the installed sender on each run. The console backend is healthy ("needs no connection"); the SMTP backend connects and authenticates without sending anything. The settings page's **Test connection** button runs it.

## Tests

`simple_module_test` provides a `captured_mail` fixture that installs a recording sender for the test and restores the previous state afterwards.
Inspect `captured_mail.messages[0].attachments` (or
`captured_mail.to("a@example.com")[0].attachments`) for the DTOs and their original
content bytes.
