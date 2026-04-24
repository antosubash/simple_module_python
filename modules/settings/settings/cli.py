"""Click commands for the settings module.

Attached to the top-level ``sm`` CLI via the ``simple_module_cli`` entry-point
group (see pyproject.toml). Usage:

    sm settings import-from-env
"""

from __future__ import annotations

import asyncio
import os

import click
from fastapi import FastAPI

from settings.constants import MODULE_PACKAGE
from settings.env_vars import env_prefix_for
from settings.hydrate import value_type_for_field
from settings.store import SettingsStore


@click.group("settings", context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """Settings module administration."""


async def import_from_env_impl(app: FastAPI, store: SettingsStore) -> int:
    """Write a SYSTEM override for every ``SM_<PREFIX>_<FIELD>`` env var set.

    Returns the count of overrides written. Env vars that don't match a
    registered field are ignored.
    """
    registry = getattr(app.state, MODULE_PACKAGE).module_registry
    count = 0
    for package, module_cls in registry.items():
        prefix = env_prefix_for(package)
        for field_name in module_cls.model_fields:
            raw = os.environ.get(f"{prefix}{field_name.upper()}")
            if raw is None:
                continue
            vtype = value_type_for_field(module_cls, field_name)
            await store.set_override(package, field_name, raw, vtype)
            count += 1
    return count


@cli.command("import-from-env")
def import_from_env() -> None:
    """Import every ``SM_<PREFIX>_<FIELD>`` env var as a SYSTEM override."""
    from simple_module_hosting.app_builder import create_app
    from simple_module_hosting.settings import Settings

    from settings.service import SettingService

    fastapi_app = create_app(Settings())

    async def run() -> None:
        async with (
            fastapi_app.router.lifespan_context(fastapi_app),
            fastapi_app.state.sm.db.session_factory() as session,
        ):
            store = SettingsStore(SettingService(session))
            n = await import_from_env_impl(fastapi_app, store)
            await session.commit()
            click.secho(f"Imported {n} override(s) from environment.", fg="green")

    asyncio.run(run())


if __name__ == "__main__":
    cli()
