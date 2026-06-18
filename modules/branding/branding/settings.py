"""Branding module settings — DB-backed via ``register_module_settings``.

The four values an administrator can customise (app name, logo, favicon,
primary colour) are stored in the shared settings store at SYSTEM scope,
hydrated into ``app.state.branding.settings`` at boot, and hot-swapped on save
through ``settings.reload.apply_changes_and_reload``.

Logo/favicon are stored as ``file_storage`` UUIDs (empty string = unset); the
frontend derives a download URL from the id.
"""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from branding.constants import HEX_COLOR_RE, MAX_APP_NAME_LEN

DEFAULT_APP_NAME = "SimpleModule"


class BrandingSettings(BaseSettings):
    """Customisable application identity."""

    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = DEFAULT_APP_NAME
    primary_color: str = ""  # "" = use the theme default; otherwise "#rrggbb"
    logo_file_id: str = ""  # file_storage UUID, "" = no custom logo
    favicon_file_id: str = ""  # file_storage UUID, "" = no custom favicon

    @field_validator("app_name")
    @classmethod
    def _non_empty_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("app_name must not be blank")
        if len(cleaned) > MAX_APP_NAME_LEN:
            raise ValueError(f"app_name must be at most {MAX_APP_NAME_LEN} characters")
        return cleaned

    @field_validator("primary_color")
    @classmethod
    def _valid_hex(cls, value: str) -> str:
        if value and not HEX_COLOR_RE.match(value):
            raise ValueError("primary_color must be a #rrggbb hex string or empty")
        return value.lower()
