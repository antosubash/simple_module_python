# simple_module_mail

Outgoing mail for `simple_module` apps. The module owns the transport (SMTP via
`aiosmtplib`, or a console backend that logs each message) and its settings, and
installs a process-level sender that any module can use through
`simple_module_core.mail` without knowing whether mail is configured.

The default backend is `console`: messages are logged, nothing is delivered.
Switch to `smtp` and fill in the server details to deliver real email.

## Install

Add the package to your host and re-sync. Discovery picks it up from the
`simple_module` entry point, no host code changes:

```toml
# host/pyproject.toml
dependencies = ["simple_module_mail"]
```

```bash
uv sync --all-packages
```

## Usage

1. Sign in as an admin and open **Settings -> Modules -> Mail**.
2. Set `backend` to `smtp` and fill `smtp_host`, `smtp_port`, `smtp_username`,
   `smtp_password` (masked in the UI), `smtp_from` and `smtp_tls`. Saving
   rebuilds the sender live, no restart needed.
3. Use **Test connection** to run the `mail.smtp` health check. It logs in to
   the server and hangs up without sending anything.

From code, send through the core interface:

```python
from simple_module_core.mail import MailMessage, current_mail_sender

await current_mail_sender().send(
    MailMessage(to="a@example.com", subject="Hello", text="Plain body")
)
```

Code that may run in the outbox worker (no `app`) calls
`await resolve_mail_sender(db)` instead; the module installs a resolver that
builds the sender from the stored settings. `sender.delivers_email` is `False`
for the console backend, so screens can fall back to showing a link.

Settings stored by earlier versions as `users.mailer` / `users.smtp_*` are moved
to `mail.backend` / `mail.smtp_*` by a data migration.
