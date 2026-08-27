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
from pydantic_settings import SettingsConfigDict
from simple_module_core.settings_base import DbBackedSettings

from branding.constants import (
    BANNER_SEVERITY_INFO,
    DESIGN_PACK_ERROR,
    DESIGN_PACK_RE,
    HEX_COLOR_RE,
    clean_app_name,
    clean_banner_message,
    normalize_banner_severity,
)

DEFAULT_APP_NAME = "SimpleModule"


class BrandingSettings(DbBackedSettings):
    """Customisable application identity."""

    # ``DbBackedSettings`` (not ``BaseSettings``) so the DB is genuinely the
    # only source: omitting ``env_prefix`` would leave pydantic-settings
    # reading each field from its bare name — GH #283.
    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = DEFAULT_APP_NAME
    primary_color: str = ""  # "" = use the theme default; otherwise "#rrggbb"
    logo_file_id: str = ""  # file_storage UUID, "" = no custom logo
    # Variant for the app's always-dark surfaces (sidebar, mobile bar). Unset
    # falls back to ``logo_file_id``, so a deployment that only ever uploads one
    # logo behaves exactly as before.
    logo_dark_file_id: str = ""
    favicon_file_id: str = ""  # file_storage UUID, "" = no custom favicon
    design_pack: str = ""  # "" = base tokens only; otherwise a registered slug
    banner_message: str = ""  # "" = no site-wide banner
    banner_severity: str = BANNER_SEVERITY_INFO

    @field_validator("app_name")
    @classmethod
    def _non_empty_name(cls, value: str) -> str:
        return clean_app_name(value)

    @field_validator("primary_color")
    @classmethod
    def _valid_hex(cls, value: str) -> str:
        if value and not HEX_COLOR_RE.match(value):
            raise ValueError("primary_color must be a #rrggbb hex string or empty")
        return value.lower()

    @field_validator("banner_message")
    @classmethod
    def _bounded_banner(cls, value: str) -> str:
        return clean_banner_message(value)

    @field_validator("banner_severity")
    @classmethod
    def _known_severity(cls, value: str) -> str:
        # Normalise rather than reject: these hydrate from the DB at boot, where
        # an unknown severity must degrade to a readable banner, not stop the
        # app. The update DTO is the strict one.
        return normalize_banner_severity(value)

    @field_validator("design_pack")
    @classmethod
    def _valid_pack_slug(cls, value: str) -> str:
        # Shape only — whether a module still provides this pack is checked in
        # the endpoint. These settings are also hydrated from the DB at boot,
        # where a pack whose module has since been uninstalled must degrade to
        # an unstyled site rather than refuse to start.
        if value and not DESIGN_PACK_RE.match(value):
            raise ValueError(DESIGN_PACK_ERROR)
        return value
