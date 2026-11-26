"""``schema status``."""

from __future__ import annotations

import hashlib

import click

from simple_module_remote.commands.runtime import SCHEMA_BUNDLED, state_of

__all__ = ["schema_fingerprint", "schema_group"]

FINGERPRINT_CHARS = 12


def schema_fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:FINGERPRINT_CHARS]


def schema_info(root: dict) -> str:
    info = root.get("info")
    version = info.get("version") if isinstance(info, dict) else None
    return str(version) if version else "unknown"


@click.group("schema", help="Inspect the command schema.")
def schema_group() -> None:
    pass


@schema_group.command("status", help="Show where the schema comes from and its version.")
@click.pass_context
def status(ctx: click.Context) -> None:
    state = state_of(ctx)
    click.echo(f"source:      {SCHEMA_BUNDLED}")
    click.echo(f"path:        {state.schema_path}")
    click.echo(f"version:     {schema_info(state.root)}")
    click.echo(f"fingerprint: {schema_fingerprint(state.schema_path.read_bytes())}")
