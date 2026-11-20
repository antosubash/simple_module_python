"""One-shot migration of legacy environment variables into DB settings."""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Mapping, Sequence
from typing import Annotated

import typer
from fastapi import FastAPI
from pydantic import ValidationError
from simple_module_core.dotenv import find_env_file, parse_dotenv
from simple_module_core.module_settings import module_settings_registry
from simple_module_core.settings_hydrate import value_type_for_field
from simple_module_core.stored_settings import parse_stored_value

from settings.core.env_vars import env_prefix_for
from settings.module_settings.store import SettingsStore

app = typer.Typer(help="Settings module administration.", no_args_is_help=True)


@app.callback()
def settings_commands() -> None:
    """Keep the command group when used standalone or mounted under smpy."""


def _validation_message(message: str, environ: Mapping[str, str]) -> str:
    # Validator messages can interpolate inputs even when include_input=False.
    values = {
        variant
        for raw in environ.values()
        if raw
        for normalized in (raw, raw.upper(), raw.lower())
        for variant in (normalized, repr(normalized))
    }
    if not values:
        return message
    pattern = "|".join(re.escape(value) for value in sorted(values, key=len, reverse=True))
    return re.sub(pattern, "[redacted]", message)


async def import_from_env_impl(
    app_inst: FastAPI,
    store: SettingsStore,
    environ: Mapping[str, str] | None = None,
    *,
    only: Sequence[str] = (),
    prefixes: Sequence[str] = (),
) -> int:
    """Validate a selected batch, then write SYSTEM overrides and print names.

    The project .env is overlaid by process env (real env wins). Filters are
    additive. Only registered DB settings fields are eligible: there is no
    general env-only field marker. Any validation failure aborts all writes.
    """
    if environ is None:
        environ = {**parse_dotenv(find_env_file()), **os.environ}
    registry = module_settings_registry(app_inst)
    selected = {name.lower() for name in only}
    known = {name.lower() for name in registry.all_packages()}
    if unknown := selected - known:
        raise typer.BadParameter(
            f"Unknown module(s): {', '.join(sorted(unknown))}. "
            f"Known modules: {', '.join(registry.all_packages())}",
            param_hint="--only",
        )
    prefixes = tuple(prefix.upper() for prefix in prefixes)

    def matches(package: str, env_name: str) -> bool:
        return (
            not (selected or prefixes)
            or package.lower() in selected
            or env_name.startswith(prefixes)
        )

    known_vars: set[str] = set()
    pending: list[tuple[str, str, str, str]] = []
    failed = False
    for package, cls in registry.items():
        prefix = env_prefix_for(package)
        candidates = {}
        for field_name in cls.model_fields:
            env_name = f"{prefix}{field_name.upper()}"
            known_vars.add(env_name)
            if env_name in environ and matches(package, env_name):
                candidates[field_name] = (environ[env_name], value_type_for_field(cls, field_name))
        if not candidates:
            continue
        merged = {}
        parse_failed = False
        existing = await store.get_overrides(package)
        redactions = {**environ, **{name: raw for name, (raw, _) in existing.items()}}
        for field_name, (raw, vtype) in existing.items():
            if field_name in cls.model_fields and field_name not in candidates:
                try:
                    merged[field_name] = parse_stored_value(raw, vtype)
                except ValueError:
                    typer.echo(
                        f"Error {package}.{field_name}: existing DB value cannot parse as {vtype}.",
                        err=True,
                    )
                    parse_failed = failed = True
        for field_name, (raw, vtype) in candidates.items():
            try:
                merged[field_name] = parse_stored_value(raw, vtype)
            except ValueError:
                typer.echo(
                    f"Error {prefix}{field_name.upper()}: cannot parse as {vtype}.", err=True
                )
                parse_failed = failed = True
        if parse_failed:
            continue
        try:
            cls(**merged)
        except ValidationError as exc:
            failed = True
            for error in exc.errors(include_input=False, include_context=False, include_url=False):
                loc = error["loc"]
                fields = [str(loc[0])] if loc and loc[0] in candidates else list(candidates)
                for field_name in fields:
                    message = _validation_message(error["msg"], redactions)
                    typer.echo(f"Error {prefix}{field_name.upper()}: {message}", err=True)
            continue
        pending.extend((package, name, raw, vtype) for name, (raw, vtype) in candidates.items())

    selected_prefixes = tuple(env_prefix_for(name) for name in known if name in selected)
    for env_name in sorted(environ):
        if (
            env_name.startswith("SM_")
            and env_name not in known_vars
            and (not (selected or prefixes) or env_name.startswith(selected_prefixes + prefixes))
        ):
            typer.echo(
                f"Skipped {env_name}: no registered DB settings field (env-only or unknown)."
            )
    if failed:
        raise typer.Exit(code=1)
    for package, field_name, raw, vtype in pending:
        await store.set_override(package, field_name, raw, vtype)
        typer.echo(f"Stored {package}.{field_name}")
    return len(pending)


@app.command("import-from-env")
def import_from_env(
    only: Annotated[
        list[str] | None, typer.Option("--only", help="Settings package to import; repeatable.")
    ] = None,
    prefix: Annotated[
        list[str] | None,
        typer.Option("--prefix", help="Environment variable prefix to import; repeatable."),
    ] = None,
) -> None:
    """Validate and import selected SM_<PREFIX>_<FIELD> variables into the DB."""
    from simple_module_hosting.app_builder import create_app
    from simple_module_hosting.settings import Settings

    from settings.core.service import SettingService

    fastapi_app = create_app(Settings())

    async def run() -> int:
        async with (
            fastapi_app.router.lifespan_context(fastapi_app),
            fastapi_app.state.sm.db.session_factory() as session,
        ):
            store = SettingsStore(SettingService(session))
            try:
                n = await import_from_env_impl(
                    fastapi_app, store, only=only or (), prefixes=prefix or ()
                )
            except typer.Exit:
                typer.echo("Imported 0 override(s) from environment.")
                raise
            await session.commit()
            typer.echo(f"Imported {n} override(s) from environment.")
            if n == 0 and find_env_file().is_file():
                typer.echo(
                    "Hint: variables must be named SM_<MODULE>_<FIELD> "
                    "(e.g. SM_MAIL_SMTP_PORT); none in the environment or .env matched the filters."
                )
        return 0

    raise typer.Exit(code=asyncio.run(run()))
