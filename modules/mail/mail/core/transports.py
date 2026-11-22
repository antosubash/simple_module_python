"""Process-local factories, registered in hooks shared by web and workers."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from simple_module_core.mail import ConsoleMailSender, MailSender
from simple_module_core.settings_base import DbBackedSettings

from mail.core import constants as c

logger = logging.getLogger(__name__)
MailTransportFactory = Callable[[Any, bool], MailSender]


@dataclass(frozen=True)
class MailTransport:
    factory: MailTransportFactory
    settings_model: type[DbBackedSettings] | None = None
    package: str | None = None


def _console(settings: Any, log_bodies: bool) -> MailSender:
    return ConsoleMailSender(include_body=log_bodies)


def _smtp(settings: Any, log_bodies: bool) -> MailSender:
    from mail.delivery.sender import SmtpMailSender

    return SmtpMailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        from_address=settings.smtp_from,
        use_tls=settings.smtp_tls,
        tls_mode=settings.smtp_tls_mode,
    )


_transports: dict[str, MailTransport] = {
    c.BACKEND_CONSOLE: MailTransport(_console),
    c.BACKEND_SMTP: MailTransport(_smtp),
}
# Shared with field metadata so the generic admin select sees later registrations.
TRANSPORT_NAMES = sorted(_transports)


def register_mail_transport(
    name: str,
    factory: MailTransportFactory,
    *,
    settings_model: type[DbBackedSettings] | None = None,
    package: str | None = None,
) -> None:
    """Register a synchronous factory(options, log_bodies) in each process.

    Call in ``register_event_handlers`` before returning for ``app is None``.
    With a settings model, *package* names its registered module settings;
    otherwise the factory receives ``MailSettings``. Identical registration
    is idempotent; conflicting names (including built-ins) are rejected.
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        raise ValueError("Mail transport names must be lowercase slugs")
    if (settings_model is None) != (package is None):
        raise ValueError("Mail transport settings_model and package must be supplied together")
    if settings_model is not None and not issubclass(settings_model, DbBackedSettings):
        raise TypeError("Mail transport settings must inherit DbBackedSettings")
    transport = MailTransport(factory, settings_model, package)
    if name in _transports and _transports[name] != transport:
        raise ValueError(f"Mail transport {name!r} is already registered")
    _transports[name] = transport
    TRANSPORT_NAMES[:] = sorted(_transports)


def get_mail_transport(name: str, *, development: bool = False) -> MailTransport:
    """Fail clearly for a missing provider; development may log instead."""
    if name in _transports:
        return _transports[name]
    message = (
        f"Unknown mail transport {name!r}; registered transports: {', '.join(TRANSPORT_NAMES)}"
    )
    if not development:
        raise ValueError(message)
    logger.warning("%s; falling back to console", message)
    return _transports[c.BACKEND_CONSOLE]
