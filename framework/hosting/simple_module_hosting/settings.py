"""Back-compat shim — prefer BootstrapSettings + HostSettings directly."""

from __future__ import annotations

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.host_settings import HostSettings


class Settings(HostSettings, BootstrapSettings):
    """Combined bootstrap + host settings for legacy import sites."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Restore the default sources that ``HostSettings`` removes.

        ``HostSettings`` is a ``DbBackedSettings``, which drops the env source
        so its fields can't be set by bare names (GH #283). It comes first in
        this shim's MRO, so without this override the *bootstrap* half loses
        its environment too — and ``SM_DATABASE_URL``, ``SM_SECRET_KEY`` and
        ``SM_AUTH_PROVIDER`` are read from the environment by design, before
        any database exists to read them from.

        Restoring pydantic's default ordering keeps this shim behaving exactly
        as it did: every field resolves under ``BootstrapSettings``' own
        ``env_prefix="SM_"``, so the names are namespaced either way.
        """
        return (init_settings, env_settings, dotenv_settings, file_secret_settings)
