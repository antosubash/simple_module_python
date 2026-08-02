"""Catalog module settings (DB-backed).

Values come from the pydantic defaults below at boot, then get hydrated from
the settings store by the hosting lifespan before module ``on_startup`` runs.
Runtime changes go through ``settings.reload.apply_changes_and_reload``.

``extra="ignore"`` keeps an unknown stored key from breaking boot after a
field is removed.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from catalog.constants import DEFAULT_PAGE_SIZE


class CatalogSettings(BaseSettings):
    """Configuration for the catalog module."""

    model_config = SettingsConfigDict(extra="ignore")

    default_page_size: int = DEFAULT_PAGE_SIZE
