# Mail module and tenant invitation emails (GH #496)

Status: approved 2026-10-20.

## Problem

`tenants` publishes `InvitationCreated` "for a mailer module to send", but nothing
subscribes, so invitations reach nobody unless the admin copies the link by hand.
The only mailer lives inside `users`, and its `Mailer` protocol has one method per
users flow, so another module cannot reuse it. Keycloak installs have no `users`
and therefore no mail at all.

## Decisions

- SMTP transport and its settings move into a new **`mail` plugin module**
  (`simple_module_mail`). The framework core gets only the interface.
- Tenant invitation emails go through the **durable outbox when
  `background_tasks` is installed** (retried, at-least-once), and are sent from
  the request's after-commit callback otherwise.
- Mail stays plain text and English, like `users` today. HTML and translated
  mail are out of scope.

## 1. Core interface: `simple_module_core.mail`

```python
@dataclass(frozen=True)
class MailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None


class MailSender(Protocol):
    delivers_email: bool  # False for a sender that only logs

    async def send(self, message: MailMessage) -> None: ...


class ConsoleMailSender:  # delivers_email = False; logs to "simple_module.mail"
    ...


MailSenderResolver = Callable[[Any], Awaitable[MailSender]]  # takes an AsyncSession

def install_mail_sender(sender: MailSender | None) -> None: ...
def install_mail_resolver(resolver: MailSenderResolver | None) -> None: ...
def current_mail_sender() -> MailSender: ...  # installed sender, else ConsoleMailSender
async def resolve_mail_sender(db: Any | None = None) -> MailSender: ...
```

Process-level state, because the outbox worker builds modules without an app
(`register_event_handlers(bus, None)`), so a durable handler cannot reach
`app.state`:

- `install_mail_sender` sets the sender of a web process (built from cached
  settings, rebuilt on `settings_reloaded`). `current_mail_sender()` is sync so
  views can ask `delivers_email` while rendering.
- `install_mail_resolver` sets an async factory that builds a sender from the DB.
  It is used by `resolve_mail_sender(db)` only when no sender is installed (the
  worker). With neither, both functions return a `ConsoleMailSender`, so callers
  never need to check whether mail is configured.
- The fallback console sender (nothing installed) logs recipient and subject
  only, at WARNING: bodies carry one-time tokens. The `mail` module's explicit
  `console` backend logs the whole message, as `users` did, for development.
- No settings and no SMTP code in core; SM009 holds.

## 2. `mail` plugin module (`modules/mail/mail/`)

- `MailSettings(DbBackedSettings)`: `backend: Literal["console", "smtp"] = "console"`,
  `smtp_host`, `smtp_port = 587`, `smtp_username`, `smtp_password`,
  `smtp_from = "no-reply@localhost"`, `smtp_tls = True`. Registered with
  `register_module_settings`; edited on the generic settings page.
- `SmtpMailSender` (aiosmtplib, the existing code moved from `users`, plus
  `verify_connection()`), `build_sender(settings)`.
- Lifecycle: `register_settings` mounts `app.state.mail`; `on_startup` installs
  the sender; `settings_reloaded` rebuilds and reinstalls it; `on_shutdown`
  uninstalls. `register_event_handlers` installs the resolver (it runs in the
  worker too) — it hydrates `MailSettings` from the given session.
- Health check `mail.smtp` (on demand, `probe=False`) replaces `users.mailer`;
  the settings page's "Test mailer connection" button points at it.
- No tables, no pages. Full module checklist: pyproject metadata, README,
  `docs/modules/mail.md`, docs index + sidebar, release matrix, root
  `testpaths`/`extra-paths`, host dependency, CHANGELOG.

### Settings data migration

Data-only Alembic revision on the users trunk: for system-scope rows of the
settings table, `users.mailer` → `mail.backend` and `users.smtp_*` →
`mail.smtp_*` (same suffix). The downgrade reverses it. An existing `mail.*`
row wins over a `users.*` one (the old row is then deleted), so a re-run is safe.

## 3. `users`

- `UsersSettings` loses `mailer` and `smtp_*`; keeps `base_url`.
- `Mailer` protocol unchanged (third-party mailers keep working). The built-in
  implementation renders the existing templates and subjects and sends through
  `current_mail_sender()` at send time, so a settings change takes effect
  without a restart. `delivers_email` is a property reading the current sender.
  `ConsoleMailer` and `SmtpMailer` are folded into it.
- `mailer_delivers`, the bulk/resend invite fallbacks and the test doubles keep
  their behaviour. The `users.mailer` health check moves to `mail`.
- `simple_module_users` depends on `simple_module_mail` (pyproject), so an
  upgrade does not silently lose SMTP.

## 4. `tenants`

- After creating an invitation, `InvitationService.create`:
  - if `bus.durable_transport` is set, `publish_durable(InvitationCreated(...), db)`
    in the request transaction, handled by the durable handler
    `tenants.send_invitation_email` (registered before any `app is None` return);
  - otherwise sends from the existing after-commit callback. A failure there
    logs a warning; the invitation still exists and the link is still shown.
  - The in-process `InvitationCreated` publish is unchanged.
- The handler resolves the sender with `resolve_mail_sender(ctx.db)` and renders
  `tenants/templates/invitation.txt` (stdlib `string.Template`; no new dependency)
  with tenant name, role and link.
- A root-relative `accept_url` (no `public_base_url`) is not emailed: the handler
  logs a warning naming the setting, since a relative link is useless in a mail.
- `InvitationIssued` gains `emailed: bool` = the current sender delivers and the
  link is absolute. `InviteForm` shows "Invitation emailed to …" or "Email isn't
  configured — share this link"; the copy button stays. New i18n keys.
- `docs/modules/tenants.md` corrected.

## 5. Tests

- `captured_mail` fixture in `simple_module_test`: installs a recording sender,
  restores the previous state afterwards; an autouse reset so process-level
  state never leaks between tests.
- Core: resolution order (installed → resolver → console).
- mail: settings → sender, reload reinstalls, resolver hydrates from DB, health
  check; migration up/down.
- users: existing flows pass against `captured_mail`.
- tenants: emailed via on-commit path; emailed via durable handler; relative
  link not emailed; send failure keeps the invitation; `emailed` flag.
- Vitest: both InviteForm states.
