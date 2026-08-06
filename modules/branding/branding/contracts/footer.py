"""Footer DTOs — the public surface for the configurable site footer.

Mirrors IIASA.GeoWiki's ``FooterDto`` / ``FooterColumnDto`` / ``FooterLinkDto``
/ ``FooterSocialLinkDto``. A footer update replaces the whole structure, as it
does there — partial merges into nested lists have no obvious semantics.
"""

from __future__ import annotations

from pydantic import field_validator
from sqlmodel import SQLModel

from branding.footer import (
    MAX_COLUMNS,
    MAX_LINKS_PER_COLUMN,
    MAX_SOCIAL_LINKS,
    clean_label,
    clean_text,
    validate_href,
)


class FooterLink(SQLModel):
    """One labelled link, in a column or in the social row."""

    label: str
    href: str

    @field_validator("label")
    @classmethod
    def _label(cls, value: str) -> str:
        return clean_label(value)

    @field_validator("href")
    @classmethod
    def _href(cls, value: str) -> str:
        # Admin-authored and rendered into an anchor on every page, so the
        # scheme allow-list here is what keeps `javascript:` out.
        return validate_href(value)


class FooterColumn(SQLModel):
    """A titled group of links."""

    title: str
    links: list[FooterLink] = []

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return clean_label(value, what="title")

    @field_validator("links")
    @classmethod
    def _bounded(cls, value: list[FooterLink]) -> list[FooterLink]:
        if len(value) > MAX_LINKS_PER_COLUMN:
            raise ValueError(f"A column can have at most {MAX_LINKS_PER_COLUMN} links")
        return value


class FooterConfig(SQLModel):
    """The whole configurable footer."""

    tagline: str = ""
    copyright_owner: str = ""
    note: str = ""
    columns: list[FooterColumn] = []
    social_links: list[FooterLink] = []

    @field_validator("tagline", "copyright_owner", "note")
    @classmethod
    def _text(cls, value: str) -> str:
        return clean_text(value)

    @field_validator("columns")
    @classmethod
    def _bounded_columns(cls, value: list[FooterColumn]) -> list[FooterColumn]:
        if len(value) > MAX_COLUMNS:
            raise ValueError(f"A footer can have at most {MAX_COLUMNS} columns")
        return value

    @field_validator("social_links")
    @classmethod
    def _bounded_social(cls, value: list[FooterLink]) -> list[FooterLink]:
        if len(value) > MAX_SOCIAL_LINKS:
            raise ValueError(f"A footer can have at most {MAX_SOCIAL_LINKS} social links")
        return value
