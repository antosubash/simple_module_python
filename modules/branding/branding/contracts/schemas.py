"""SQLModel DTOs for the Branding module — the public surface."""

from __future__ import annotations

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from branding.constants import (
    DESIGN_PACK_ERROR,
    DESIGN_PACK_RE,
    HEX_COLOR_RE,
    MAX_APP_NAME_LEN,
    clean_app_name,
)


class BrandingOut(SQLModel):
    """Current branding, with logo/favicon resolved to download URLs."""

    app_name: str
    primary_color: str = ""
    design_pack: str = ""
    logo_url: str | None = None
    favicon_url: str | None = None


class BrandingUpdate(SQLModel):
    """Editable text fields. Logo/favicon are set via dedicated upload routes."""

    app_name: str | None = Field(default=None, max_length=MAX_APP_NAME_LEN)
    primary_color: str | None = Field(default=None)
    design_pack: str | None = Field(default=None)

    @field_validator("app_name")
    @classmethod
    def _non_empty_name(cls, value: str | None) -> str | None:
        # Validate here so bad input surfaces as a 422 rather than a 500 when
        # BrandingSettings re-validates (blank, too long, or control chars —
        # the last would otherwise break email Subject headers downstream).
        if value is None:
            return None
        return clean_app_name(value)

    @field_validator("primary_color")
    @classmethod
    def _valid_hex(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value != "" and not HEX_COLOR_RE.match(value):
            raise ValueError("primary_color must be a #rrggbb hex string or empty")
        return value.lower()

    @field_validator("design_pack")
    @classmethod
    def _valid_pack_slug(cls, value: str | None) -> str | None:
        # Shape only, so a malformed slug is a 422 rather than a 500 when
        # BrandingSettings re-validates. Registration is checked in the
        # endpoint, which can reach ``app.state.design_packs``.
        if value is None:
            return None
        if value != "" and not DESIGN_PACK_RE.match(value):
            raise ValueError(DESIGN_PACK_ERROR)
        return value
