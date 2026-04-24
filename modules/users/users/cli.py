"""Click commands for the users module.

Attached to the top-level ``sm`` CLI via the ``simple_module_cli`` entry-point
group (see pyproject.toml). Usage:

    sm users create-admin --email a@b.test --password sekret [--full-name Me]
    sm users create-admin --email a@b.test --password new --force
"""

from __future__ import annotations

import asyncio
import logging

import click
from simple_module_hosting.settings import Settings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from users.bootstrap import create_admin


@click.group("users", context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """Users module administration."""


@cli.command("create-admin")
@click.option("--email", "-e", required=True, help="Admin email address.")
@click.option(
    "--password",
    "-p",
    required=True,
    prompt=True,
    hide_input=True,
    help="Admin password (prompted if omitted).",
)
@click.option("--full-name", default=None, help="Optional display name.")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Update the password even if this admin already exists.",
)
def create_admin_cli(email: str, password: str, full_name: str | None, force: bool) -> None:
    """Create (or update, with --force) an admin user."""
    logging.basicConfig(level=logging.INFO)

    async def _run() -> int:
        settings = Settings()
        engine = create_async_engine(settings.database_url)
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
                click.secho(f"Created admin {email} (id={result.user.id})", fg="green")
            elif force:
                click.secho(f"Updated admin {email} (id={result.user.id})", fg="green")
            else:
                click.secho(
                    f"User {email} already exists. Pass --force to reset password.",
                    fg="red",
                    err=True,
                )
                return 1
            return 0
        finally:
            await engine.dispose()

    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    cli()
