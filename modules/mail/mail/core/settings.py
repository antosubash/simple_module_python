"""Mail module settings — DB-backed via ``register_module_settings``.

``smtp_password`` is masked by the settings UI because its name matches the
secret-field pattern (``simple_module_core.settings.secret_fields.is_secret_field``).
"""

from __future__ import annotations

from email.errors import HeaderParseError
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict
from simple_module_core.mailer.mail import parse_mailbox, smtp_address_header
from simple_module_core.settings.settings_base import DbBackedSettings

from mail.core import constants as c
from mail.core.transports import TRANSPORT_NAMES


class MailSettings(DbBackedSettings):
    """Which transport sends mail, and the SMTP account it uses."""

    # ``DbBackedSettings`` so the DB is the only source (GH #283).
    model_config = SettingsConfigDict(extra="ignore")

    # Keep unknown stored names intact: lenient hydration must not silently
    # turn an uninstalled production provider into successful console delivery.
    backend: str = Field(default=c.BACKEND_CONSOLE, json_schema_extra={"choices": TRANSPORT_NAMES})
    smtp_host: str = ""
    smtp_port: int = Field(default=c.DEFAULT_SMTP_PORT, ge=c.MIN_PORT, le=c.MAX_PORT)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = Field(
        default=c.DEFAULT_FROM,
        json_schema_extra={"persist_normalized": True},
        description="One sender mailbox: addr or Display Name <addr>; "
        "at most 254 address characters and 320 total. Cannot be blank.",
    )

    @field_validator("smtp_from")
    @classmethod
    def _check_smtp_from(cls, value: str) -> str:
        error = (
            "smtp_from must be one mailbox (addr or Display Name <addr>) with a local part "
            "and domain, at most 254 address characters and 320 total, "
            "without control characters; blank is not allowed"
        )
        # Reject controls before trimming can hide them.
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError(error)
        value = value.strip()
        if not value or len(value) > 320:
            raise ValueError(error)
        try:
            address = parse_mailbox(value, allow_smtputf8=True)
            smtp_address_header(value)
        # The stdlib parser also raises these for incomplete quotes/domain literals.
        except (ValueError, HeaderParseError, IndexError, AttributeError) as exc:
            raise ValueError(error) from exc
        if len(address.addr_spec) > 254:
            raise ValueError(error)
        return value

    smtp_tls: bool = True
    smtp_tls_mode: Literal["auto", "starttls", "implicit"] = Field(
        default=c.SMTP_TLS_AUTO,
        description="auto: implicit TLS on 465, STARTTLS elsewhere; starttls or implicit: "
        "force that mode on any port. Ignored when smtp_tls is false.",
    )
