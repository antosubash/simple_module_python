"""{{MODULE_NAME}} module settings.

Per-module env-var prefix is ``SM_{{PACKAGE_NAME_UPPER}}_*``. Add fields here
as the module grows; the framework wires them onto
``app.state.{{PACKAGE_NAME}}`` via ``register_settings``.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class {{MODULE_NAME}}Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SM_{{PACKAGE_NAME_UPPER}}_", extra="ignore")
