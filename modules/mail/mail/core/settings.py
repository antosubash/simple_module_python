"""Mail module settings — DB-backed via ``register_module_settings``.

``smtp_password`` is masked by the settings UI because its name matches the
secret-field pattern (``simple_module_core.settings.secret_fields.is_secret_field``).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict
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
    smtp_from: str = c.DEFAULT_FROM
    smtp_tls: bool = True
