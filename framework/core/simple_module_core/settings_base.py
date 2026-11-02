"""Base class for DB-backed settings that must not read the environment.

Module and host settings are hydrated from the settings store at boot and
hot-swapped through ``settings.reload.apply_changes_and_reload``. The DB is
meant to be the only source of truth for them.

Subclassing ``BaseSettings`` and simply omitting ``env_prefix`` does **not**
achieve that. pydantic-settings still installs its env source; without a
prefix it resolves each field from the bare, case-insensitive *field name*.
So a class with a ``password`` field reads ``$password``, one with a
``backend`` field reads ``$backend``, and one with a ``base_url`` field reads
``$base_url`` — names generic enough that an unrelated component setting them
silently reconfigures the app, and the DB is the source of truth only when
nobody happens to have them in the environment. That was GH #283, reported
against ``background_tasks`` but true of every bundled settings class.

``DbBackedSettings`` drops the env, dotenv and secrets sources, leaving only
values passed to the constructor. Settings that genuinely must be readable
before any DB row exists — ``BackgroundTasksSettings``, whose broker URL a
worker process needs and which the production validator rejects at the
localhost default — subclass ``BaseSettings`` directly *and* declare an
explicit ``env_prefix``, so the names they read are namespaced and documented.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

__all__ = ["DbBackedSettings"]


class DbBackedSettings(BaseSettings):
    """A ``BaseSettings`` whose values come from the constructor and the DB only."""

    model_config = SettingsConfigDict(extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Init args only — no env, no ``.env``, no Docker secrets files."""
        return (init_settings,)
