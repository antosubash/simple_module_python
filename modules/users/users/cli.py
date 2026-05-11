"""Command-line entry points for the users module.

Exposed via ``smpy users`` (see pyproject.toml
[project.entry-points.simple_module_cli.cli_plugins]).

    smpy users create-admin --email a@b.test --password sekret [--full-name Me]
    smpy users create-admin --email a@b.test --password new --force
"""

from __future__ import annotations

import asyncio
import logging
import sys

import typer
from simple_module_hosting.settings import Settings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from users.bootstrap import create_admin

app = typer.Typer(help="Users module administration.", no_args_is_help=True)


@app.callback()
def _main() -> None:
    """Users module administration CLI."""


@app.command("create-admin")
def create_admin_cli(
    email: str = typer.Option(..., "--email", "-e"),
    password: str = typer.Option(..., "--password", "-p", prompt=True, hide_input=True),
    full_name: str | None = typer.Option(None, "--full-name"),
    force: bool = typer.Option(
        False,
        "--force",
        help="Update the password even if this admin already exists.",
    ),
) -> None:
    """Create (or update, with --force) an admin user."""
    logging.basicConfig(level=logging.INFO)

    async def _run() -> int:
        settings = Settings()
        engine = create_async_engine(settings.database_url)
        # IMPORTANT: matches the module's own session factory
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                result = await create_admin(
                    session,
                    email=email,
                    password=password,
                    full_name=full_name,
                    force=force,
                )
            if result.created:
                typer.echo(f"Created admin {email} (id={result.user.id})")
            elif force:
                typer.echo(f"Updated admin {email} (id={result.user.id})")
            else:
                typer.echo(
                    f"User {email} already exists. Pass --force to reset password.",
                    err=True,
                )
                return 1
            return 0
        finally:
            await engine.dispose()

    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    app()
