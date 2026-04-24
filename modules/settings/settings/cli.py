"""``sm-settings`` CLI.

Exposed via ``sm-settings`` (see pyproject.toml [project.scripts]).

Subcommands:

* ``sm-settings import-from-env`` — one-shot migration that walks every
  registered module's ``BaseSettings`` and, for each field whose legacy
  ``SM_<PREFIX>_<FIELD>`` env var is set, writes a SYSTEM-scoped override
  into the Settings store.
"""

from __future__ import annotations

import asyncio
import os
from importlib.metadata import PackageNotFoundError, version

import typer
from fastapi import FastAPI

from settings.constants import MODULE_PACKAGE
from settings.env_vars import env_prefix_for
from settings.hydrate import value_type_for_field
from settings.store import SettingsStore

app = typer.Typer(
    help="Settings module administration.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _pkg_version() -> str:
    try:
        return version("simple_module_settings")
    except PackageNotFoundError:
        return "unknown"


def _version_callback(show: bool) -> None:
    if show:
        typer.echo(f"sm-settings {_pkg_version()}")
        raise typer.Exit()


@app.callback()
def _main(
    _v: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Settings module administration CLI."""


async def import_from_env_impl(app: FastAPI, store: SettingsStore) -> int:
    """Write a SYSTEM override for every ``SM_<PREFIX>_<FIELD>`` env var set.

    Returns the count of overrides written. Env vars that don't match a
    registered field are ignored.
    """
    registry = getattr(app.state, MODULE_PACKAGE).module_registry
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
    """Import every ``SM_<PREFIX>_<FIELD>`` env var as a SYSTEM override."""
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
            typer.secho(f"Imported {n} override(s) from environment.", fg="green")
        return 0

    raise typer.Exit(asyncio.run(run()))


def main() -> None:
    """Console-script entry point for ``sm-settings``."""
    app()


if __name__ == "__main__":
    main()
