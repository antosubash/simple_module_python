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
| `backend` | `console` | `console` logs the whole message (development); `smtp` delivers |
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

- `current_mail_sender()` is synchronous and never raises; with nothing installed it returns a console sender that logs only the recipient and subject (bodies carry one-time tokens).
- `sender.delivers_email` is `False` for console senders, so a screen can show a link instead of promising an inbox.
- Code that may run in the outbox worker (no `app`) uses `await resolve_mail_sender(db)`. The module installs a resolver in `register_event_handlers` before its `app is None` return; it hydrates `MailSettings` from the given session.

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
