"""``smpy openapi`` — export the host's OpenAPI document without a server (#456).

The app is built in process with ``create_app`` and its schema is written to a
file, so CI can generate API clients from a checkout. ``simple_module_hosting``
is imported inside the command: the CLI package depends only on typer and
tomlkit (``test_no_framework_deps``), and the hosting stack exists only in a
host's environment (run via ``uv run smpy openapi export``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer

openapi_app = typer.Typer(help="OpenAPI schema tools.", no_args_is_help=True)


def _norm(name: str) -> str:
    """``feature_flags`` and the ``FeatureFlags`` tag compare equal."""
    return name.replace("_", "").replace("-", "").lower()


def _filter_modules(schema: dict, modules: list[str]) -> dict:
    """Keep operations whose first tag is one of ``modules`` (case and underscores ignored)."""
    wanted = {_norm(m) for m in modules}
    paths: dict = {}
    for path, item in schema.get("paths", {}).items():
        kept = {
            method: op
            for method, op in item.items()
            if isinstance(op, dict) and _norm((op.get("tags") or [""])[0]) in wanted
        }
        if kept:
            paths[path] = kept
    return {**schema, "paths": paths}


@openapi_app.command("export")
def export(
    out: Annotated[Path, typer.Option("--out", help="File to write.")] = Path("openapi.json"),
    module: Annotated[
        list[str] | None,
        typer.Option("--module", help="Only include this module's operations. Repeatable."),
    ] = None,
) -> None:
    """Write the host's OpenAPI document (``/api/**`` only) to ``--out``."""
    project_root = Path(os.environ.get("SM_PROJECT_ROOT") or Path.cwd())
    os.environ.setdefault("SM_PROJECT_ROOT", str(project_root))

    try:
        from simple_module_core.dotenv import load_dotenv_into_environ
        from simple_module_hosting import create_app, merge_host_settings
        from simple_module_hosting._preapp_config import load_host_overrides
        from simple_module_hosting.bootstrap_settings import BootstrapSettings
    except ImportError:
        typer.echo(
            "error: simple_module_hosting is not installed — run this from a host "
            "project (`uv run smpy openapi export`).",
            err=True,
        )
        raise typer.Exit(code=1) from None

    load_dotenv_into_environ(project_root / ".env")
    if not load_host_overrides(BootstrapSettings().database_url):
        typer.echo(
            "warning: no host settings found in the database (unreachable, not migrated or "
            "empty); using environment and defaults for api_title / api_version.",
            err=True,
        )
    # Never serves requests: an unreachable database must not fail the export.
    settings = merge_host_settings(strict=False)
    schema = create_app(settings).openapi()
    if module:
        schema = _filter_modules(schema, module)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    typer.echo(f"wrote {out} ({len(schema.get('paths', {}))} paths)")
