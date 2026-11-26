"""The combined host settings object: ``HostSettings`` (DB-backed) + ``BootstrapSettings`` (env).

``Settings`` is the type most of the host and its tests use. Code that needs only
the process-wiring half or only the DB-backed half may depend on
``BootstrapSettings`` / ``HostSettings`` directly; this is not a deprecated shim.
"""

from __future__ import annotations

import secrets

from pydantic import PrivateAttr, model_validator
from simple_module_core.settings.environments import NON_PROD_ENVIRONMENTS

from simple_module_hosting.config.bootstrap_settings import BootstrapSettings
from simple_module_hosting.config.host_settings import HostSettings


class Settings(HostSettings, BootstrapSettings):
    """Combined bootstrap + host settings."""

    _secret_key_ephemeral: bool = PrivateAttr(default=False)
    _app_name_default: str | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _require_resolved_root(self) -> Settings:
        if not self.secret_key.strip():
            if self.environment not in NON_PROD_ENVIRONMENTS:
                raise ValueError("SM_SECRET_KEY resolved to an empty or whitespace-only root")
            self.secret_key = secrets.token_urlsafe(48)
        return self
