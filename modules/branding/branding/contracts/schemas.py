"""SQLModel DTOs for the Branding module — the public surface."""

from __future__ import annotations

import re

from pydantic import field_validator
from sqlmodel import Field, SQLModel

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class BrandingOut(SQLModel):
    """Current branding, with logo/favicon resolved to download URLs."""

    app_name: str
    primary_color: str = ""
    logo_url: str | None = None
    favicon_url: str | None = None


class BrandingUpdate(SQLModel):
    """Editable text fields. Logo/favicon are set via dedicated upload routes."""

    app_name: str | None = Field(default=None, min_length=1, max_length=60)
    primary_color: str | None = Field(default=None)

    @field_validator("primary_color")
    @classmethod
    def _valid_hex(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value != "" and not _HEX_COLOR.match(value):
            raise ValueError("primary_color must be a #rrggbb hex string or empty")
        return value.lower()
