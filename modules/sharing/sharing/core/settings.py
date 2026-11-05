"""Sharing module settings (DB-backed).

Values come from the pydantic defaults below at boot, then get hydrated from
the settings table by the hosting lifespan before module ``on_startup`` runs
(``register_module_settings`` in ``module.py`` records the class).
``DbBackedSettings`` reads no environment variables: the DB is the only
source. Add fields here as the module grows.
"""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict
from simple_module_core.settings_base import DbBackedSettings


class SharingSettings(DbBackedSettings):
    model_config = SettingsConfigDict(extra="ignore")
