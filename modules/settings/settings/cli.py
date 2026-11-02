"""``smpy settings`` plugin — currently only ``import-from-env``.

One-shot migration: walks every registered module's BaseSettings and
writes a SYSTEM-scoped override for each ``SM_<PREFIX>_<FIELD>`` env
var that is set.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping

import typer
from fastapi import FastAPI
from simple_module_core.dotenv import find_env_file, parse_dotenv
from simple_module_core.module_settings import module_settings_registry
from simple_module_core.settings_hydrate import value_type_for_field

from settings.env_vars import env_prefix_for
from settings.store import SettingsStore

app = typer.Typer(help="Settings module administration.", no_args_is_help=True)


async def import_from_env_impl(
    app_inst: FastAPI,
    store: SettingsStore,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Write a SYSTEM override for every ``SM_<PREFIX>_<FIELD>`` var set.

    Default source is the project ``.env`` overlaid by the process environment
    (real env wins). ``os.environ`` is never mutated.
    """
    if environ is None:
        environ = {**parse_dotenv(find_env_file()), **os.environ}
    registry = module_settings_registry(app_inst)
    count = 0
    for package, cls in registry.items():
        prefix = env_prefix_for(package)
        for field_name in cls.model_fields:
            raw = environ.get(f"{prefix}{field_name.upper()}")
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
            if n == 0 and find_env_file().is_file():
                typer.echo(
                    "Hint: variables must be named SM_<MODULE>_<FIELD> "
                    "(e.g. SM_MAIL_SMTP_PORT); none in the environment or .env matched."
                )
        return 0

    raise typer.Exit(code=asyncio.run(run()))
