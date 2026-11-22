# mail

Outgoing mail for the app. The module owns a registry of transports, including SMTP through `aiosmtplib` and a `console` backend that logs each message. Sending modules use `simple_module_core.mail`, which works whether or not this module is installed. Transport-provider modules depend on `Mail` and register through `mail.contracts`.

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
| `backend` | `console` | Registered transport name; the admin select lists all registered transports. `console` logs, `smtp` delivers |
| `smtp_host` | `""` | |
| `smtp_port` | `587` | |
| `smtp_username` | `""` | blank means no authentication |
| `smtp_password` | `""` | masked in the settings UI |
| `smtp_from` | `no-reply@localhost` | |
| `smtp_tls` | `true` | implicit TLS (`use_tls`) on port 465; mandatory STARTTLS (`start_tls`) on other ports including 587; `false` disables both |

Earlier versions kept these under `users` (`users.mailer`, `users.smtp_*`). A data migration renames the stored keys to `mail.backend` and `mail.smtp_*`; an existing `mail.*` row wins, and the downgrade reverses it.

## Custom transports

Register a synchronous `factory(options, log_bodies)` with
`register_mail_transport(name, factory, settings_model=..., package=...)` from
`mail.contracts`. The factory returns a `MailSender`: an object with
`delivers_email: bool` and `async send(message: MailMessage) -> None`.
With `settings_model` and `package`, web startup uses that package's hydrated
settings and workers hydrate the same model from the database. Without either,
the factory receives `MailSettings`. The second argument tells logging
transports whether message bodies may appear in logs.

Provider modules declare a dependency on `Mail` and register the factory in
`register_event_handlers`, **before** returning for `app is None`. This hook
runs in both the web process and the durable outbox worker. Registering only in
`on_startup` would leave workers without the transport. Names are lowercase
slugs; registering the same factory/model/package again is allowed, but
conflicting registrations (including replacements of built-ins) raise an error.
The registry is process-local, like the core mail sender, so every web and
worker process must load the provider module.

For example, an HTTP API provider can own its credentials and options in its
usual DB-backed module settings. Replace the endpoint and payload with the
provider's API and declare its HTTP client dependency in the provider package:

```python
from types import SimpleNamespace

import httpx
from mail.contracts import register_mail_transport
from pydantic import SecretStr
from simple_module_core.mail import MailMessage, validate_mail_headers
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.module_settings import register_module_settings
from simple_module_core.settings_base import DbBackedSettings

MODULE_MAIL = "Mail"
PACKAGE = "http_mail"
TRANSPORT = "http-api"


class HttpMailSettings(DbBackedSettings):
    endpoint: str = "https://api.provider.example/v1/messages"
    api_key: SecretStr = SecretStr("")
    from_address: str = "no-reply@example.com"


class HttpMailSender:
    delivers_email = True

    def __init__(self, options: HttpMailSettings, log_bodies: bool):
        self.options = options

    async def send(self, message: MailMessage) -> None:
        # This example provider supports plain messages only; never drop files.
        if message.attachments:
            raise ValueError("Configure the provider's attachment API first")
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                self.options.endpoint,
                headers={"Authorization": f"Bearer {self.options.api_key.get_secret_value()}"},
                json={
                    "from": self.options.from_address,
                    "to": message.to,
                    "subject": message.subject,
                    "text": message.text,
                    "html": message.html,
                    "reply_to": message.reply_to,
                    "headers": validate_mail_headers(message.headers),
                },
            )
            response.raise_for_status()


class HttpMailModule(ModuleBase):
    meta = ModuleMeta(name="HttpMail", depends_on=[MODULE_MAIL])

    def register_settings(self, app):
        register_module_settings(
            app, PACKAGE, HttpMailSettings, lambda s: SimpleNamespace(settings=s)
        )

    def register_event_handlers(self, bus, app):
        register_mail_transport(
            TRANSPORT, HttpMailSender, settings_model=HttpMailSettings, package=PACKAGE
        )
```

Select `http-api` under **Settings → Modules → Mail**, and set its options
under the provider's module settings. No environment variables or generic
options blob are needed. Mail settings reloads and the selected provider's
settings reloads rebuild the sender through the registry; the existing settings
invalidation path handles other web processes. Workers resolve DB settings for
each delivery. Include both `Mail` and the provider in any worker module allowlist.

An unknown transport (for example after uninstalling its provider) refuses web
startup and worker resolution outside development. In development it logs the
unknown name and falls back to console. Admin saves reject unknown names with a
field validation error. Stored unknown names are preserved during settings
hydration so they cannot silently become console delivery in production.

`install_mail_sender(sender)` remains an explicit process override and takes
precedence over the registry's configured sender, including after settings
reloads. It must be installed separately in each process that needs it; use a
registered transport for DB-configured web/worker parity. Passing `None` clears
both senders, leaving `resolve_mail_sender(db)` to use the installed resolver.

## Sending mail from a module

```python
from simple_module_core.mail import MailMessage, current_mail_sender

sender = current_mail_sender()
await sender.send(MailMessage(to="a@example.com", subject="Hi", text="Plain body"))
```

- `current_mail_sender()` is synchronous and never raises; with nothing installed it returns a console sender that logs only the recipient, subject and attachment metadata (bodies carry one-time tokens).
- `sender.delivers_email` is `False` for console senders, so a screen can show a link instead of promising an inbox.
- Code that may run in the outbox worker (no `app`) uses `await resolve_mail_sender(db)`. The module installs a resolver in `register_event_handlers` before its `app is None` return; it hydrates `MailSettings` from the given session. A worker restricted with `SM_MODULES_ENABLED` must therefore list `Mail` (and any module whose durable handler sends mail, such as `Tenants`); without it the tenants invitation handler raises, so the outbox retries the row (and marks it `dead` after its retries) instead of dropping the email.

### Message headers

SMTP generates a UTC `Date` header and a unique `Message-ID` for each outgoing
message. The ID uses the configured `From`
mailbox's domain (IDNA-encoded for internationalized domains); if it has no
parseable domain, Python's `make_msgid` chooses the local host's domain.

Pass `headers: dict[str, str]` for extra headers such as `List-Unsubscribe`:

```python
await current_mail_sender().send(
    MailMessage(
        to="subscriber@example.com",
        subject="Newsletter",
        text="This month's news",
        headers={"List-Unsubscribe": "<https://example.com/unsubscribe>"},
    )
)
```

The default is an empty dictionary, copied at construction. Names must contain
1–997 printable ASCII characters without spaces or colons. Values cannot contain
control characters other than horizontal tab, or Unicode line/paragraph separators.

Custom headers describe the message; routing, MIME, authentication and delivery
trace fields belong to the sender or receiving mail server. The following names
are rejected case-insensitively: `From`, `To`, `Cc`, `Bcc`, `Subject`, `Reply-To`,
`Date`, `Message-ID`, `MIME-Version`, `Sender`, `Return-Path`, `Received`,
`Received-SPF`, `DKIM-Signature`, `Authentication-Results`, `Delivered-To`,
`Envelope-To`, `Envelope-From`; so are all names beginning with `Content-`,
`Resent-`, `ARC-`, `X-Original-`, `X-Delivered-` or `X-Envelope-`.
Invalid headers raise `ValueError` at construction and durable deserialization.
The dictionary remains mutable despite the frozen message dataclass; SMTP
revalidates it before sending. SMTP applies headers to the outer MIME message
and explicitly derives the envelope sender from `From` and recipients from `To`
only; custom headers cannot redirect delivery.

SMTP serialization preserves unbroken ASCII URLs within the 998-byte line
limit, so long `List-Unsubscribe` URLs remain usable by mail clients. Non-ASCII
subjects and display names are encoded unless the envelope requires `SMTPUTF8`.
UTF-8 header lines are refolded when necessary to stay within the byte limit.
Console and fallback senders ignore custom headers. Custom transports should
revalidate them with `validate_mail_headers` before forwarding them through the
provider's header API, or document when unsupported.

Durable outbox events preserve custom headers; existing queued payloads without
`headers` load with an empty dictionary. The `captured_mail` fixture exposes
them as `captured_mail.messages[0].headers`.

### Reply address

Set `reply_to` when replies should reach someone other than the platform's
configured sender. For example, a booking confirmation can direct replies to
the tour guide:

```python
await current_mail_sender().send(
    MailMessage(
        to="visitor@example.com",
        subject="Your guided tour is booked",
        text="Your tour is confirmed. Reply to this email to contact your guide.",
        reply_to="guide@example.com",
    )
)
```

`reply_to` defaults to `None`. When provided, it must be one mailbox, optionally
with a display name (for example, `Guide <guide@example.com>` or
`"Doe, Jane" <guide@example.com>`). Address lists, groups, invalid addresses and
control characters, including CR/LF header injection, raise `ValueError` at
construction. SMTP adds the `Reply-To` header and keeps the configured `From`
address. Internationalized domains in SMTP address headers are IDNA-encoded
(for example, `guide@bücher.de` becomes `guide@xn--bcher-kva.de`). Domains that
cannot be IDNA-encoded in `to` or `reply_to` raise `ValueError` during message
construction and durable deserialization, before entering delivery retries.
Non-ASCII local parts (before `@`) are rejected in `reply_to`; in `to` and the
configured `From` address they require an SMTP server advertising `SMTPUTF8`.
IDN domains and non-ASCII display names alone do not require `SMTPUTF8`.
Console and fallback senders log the reply address alongside the recipient and subject.
Durable outbox events preserve it; existing queued payloads without `reply_to`
default to `None` and still send.

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
be `.` or `..`. `content_type` must be a MIME `type/subtype` without parameters;
structured `message/*` and `multipart/*` types are not supported.
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
other queued event data. Admin outbox lists omit payloads and attachment content.

## Lifecycle

| Hook | What it does |
|---|---|
| `register_settings` | `register_module_settings` mounts `app.state.mail` |
| `register_health_checks` | adds the on-demand `mail.mailer` check |
| `register_event_handlers` | installs the resolver; mail or selected-provider `SettingsReloaded` rebuilds the configured sender |
| `on_startup` | installs the sender built from the hydrated settings |
| `on_shutdown` | uninstalls the sender and the resolver |

## Health check

`mail.mailer` (`probe=False`, so it never runs on a readiness timer) re-reads the installed sender on each run. The console backend is healthy ("needs no connection"); the SMTP backend connects and authenticates without sending anything. The settings page's **Test connection** button runs it.

## Tests

`simple_module_test` provides a `captured_mail` fixture that installs a recording sender for the test and restores the previous state afterwards.
Inspect `captured_mail.messages[0].attachments` (or
`captured_mail.to("a@example.com")[0].attachments`) for the DTOs and their original
content bytes.
Inspect `captured_mail.messages[0].reply_to` (or
`captured_mail.to("visitor@example.com")[0].reply_to`) for the reply address.
