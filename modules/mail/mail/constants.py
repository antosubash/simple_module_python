"""Every literal the mail module depends on."""

from __future__ import annotations

MODULE_NAME = "Mail"
MODULE_PACKAGE = "mail"

# Dependency names must match the other modules' ``ModuleMeta.name``.
MODULE_SETTINGS = "Settings"

BACKEND_CONSOLE = "console"
BACKEND_SMTP = "smtp"

# On-demand health check; also drives the settings page's "Test connection".
CHECK_MAILER = "mail.mailer"

DEFAULT_FROM = "no-reply@localhost"
DEFAULT_SMTP_PORT = 587
MIN_PORT = 1
MAX_PORT = 65535

#: Seconds per SMTP operation (aiosmtplib defaults to 60). A send can run in a
#: request's after-commit hook, so a hung server must not hold it for a minute.
SMTP_TIMEOUT_SECONDS = 15.0
