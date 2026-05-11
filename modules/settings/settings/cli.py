"""``smpy settings`` plugin — currently only ``import-from-env``.

One-shot migration: walks every registered module's BaseSettings and
writes a SYSTEM-scoped override for each ``SM_<PREFIX>_<FIELD>`` env
var that is set.
"""

from __future__ import annotations

import asyncio
import os

import typer
from fastapi import FastAPI

from settings.constants import MODULE_PACKAGE
from settings.env_vars import env_prefix_for
from settings.hydrate import value_type_for_field
from settings.store import SettingsStore

app = typer.Typer(help="Settings module administration.", no_args_is_help=True)


async def import_from_env_impl(app_inst: FastAPI, store: SettingsStore) -> int:
    """Write a SYSTEM override for every ``SM_<PREFIX>_<FIELD>`` env var set."""
    registry = getattr(app_inst.state, MODULE_PACKAGE).module_registry
    count = 0
    for package, cls in registry.items():
        prefix = env_prefix_for(package)
        for field_name in cls.model_fields:
            raw = os.environ.get(f"{prefix}{field_name.upper()}")
            if raw is None:
                continue
            vtype = value_type_for_field(cls, field_name)
            await store.set_override(package, field_name, raw, vtype)
            count += 1
    return count


@app.command("import-from-env")
def import_from_env() -> None:
    """Write SYSTEM overrides for every SM_<PREFIX>_<FIELD> env var set."""
    from simple_module_hosting.app_builder import create_app
    from simple_module_hosting.settings import Settings

    from settings.service import SettingService

    fastapi_app = create_app(Settings())

    async def run() -> int:
        async with (
            fastapi_app.router.lifespan_context(fastapi_app),
            fastapi_app.state.sm.db.session_factory() as session,
        ):
            store = SettingsStore(SettingService(session))
            n = await import_from_env_impl(fastapi_app, store)
            await session.commit()
            typer.echo(f"Imported {n} override(s) from environment.")
        return 0

    raise typer.Exit(code=asyncio.run(run()))
