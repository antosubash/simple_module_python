"""SQLModel DTOs for the Branding module — the public surface."""

from __future__ import annotations

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from branding.constants import (
    BANNER_SEVERITIES,
    BANNER_SEVERITY_ERROR,
    DESIGN_PACK_ERROR,
    DESIGN_PACK_RE,
    HEX_COLOR_RE,
    MAX_APP_NAME_LEN,
    MAX_BANNER_MESSAGE_LEN,
    MAX_FOOTER_LINKS,
    clean_app_name,
    clean_banner_message,
    clean_footer_href,
    clean_footer_label,
)


class FooterLink(SQLModel):
    """One link in the site footer.

    Deliberately just a label and a target: the surface removed in #273 grew
    columns, social icons and a tagline, and the thing hosts actually lost was
    the ability to stop advertising the framework's repository.
    """

    label: str
    href: str

    @field_validator("label")
    @classmethod
    def _clean_label(cls, value: str) -> str:
        return clean_footer_label(value)

    @field_validator("href")
    @classmethod
    def _clean_href(cls, value: str) -> str:
        return clean_footer_href(value)


def bounded_footer_links(links: list[FooterLink]) -> list[FooterLink]:
    """Cap the list length (shared by the settings and update DTO)."""
    if len(links) > MAX_FOOTER_LINKS:
        raise ValueError(f"at most {MAX_FOOTER_LINKS} footer links may be set")
    return links


class BrandingOut(SQLModel):
    """Current branding, with logo/favicon resolved to download URLs."""

    app_name: str
    primary_color: str = ""
    design_pack: str = ""
    logo_url: str | None = None
    #: Variant for dark surfaces; ``None`` means "fall back to ``logo_url``".
    logo_dark_url: str | None = None
    favicon_url: str | None = None
    banner_message: str = ""
    banner_severity: str = ""
    #: Empty means the framework's own links are shown.
    footer_links: list[FooterLink] = Field(default_factory=list)


class BrandingUpdate(SQLModel):
    """Editable text fields. Logo/favicon are set via dedicated upload routes."""

    app_name: str | None = Field(default=None, max_length=MAX_APP_NAME_LEN)
    primary_color: str | None = Field(default=None)
    design_pack: str | None = Field(default=None)
    banner_message: str | None = Field(default=None, max_length=MAX_BANNER_MESSAGE_LEN)
    banner_severity: str | None = Field(default=None)
    #: Send ``[]`` to fall back to the framework's own links.
    footer_links: list[FooterLink] | None = Field(default=None)

    @field_validator("footer_links")
    @classmethod
    def _bounded_links(cls, value: list[FooterLink] | None) -> list[FooterLink] | None:
        return None if value is None else bounded_footer_links(value)

    @field_validator("banner_message")
    @classmethod
    def _bounded_banner(cls, value: str | None) -> str | None:
        return None if value is None else clean_banner_message(value)

    @field_validator("banner_severity")
    @classmethod
    def _known_severity(cls, value: str | None) -> str | None:
        # Strict here, unlike the settings validator: a typo'd severity should
        # be a clear 422 rather than silently becoming "info".
        if value is None:
            return None
        candidate = value.strip().lower()
        if candidate not in BANNER_SEVERITIES:
            raise ValueError(BANNER_SEVERITY_ERROR)
        return candidate

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
