"""``smpy openapi`` — export the host's OpenAPI document without a server (#456).

The app is built in process with ``create_app`` and its schema is written to a
file, so CI can generate API clients from a checkout. ``simple_module_hosting``
is imported inside the command: the CLI package depends only on typer and
tomlkit (``test_no_framework_deps``), and the hosting stack exists only in a
host's environment (run via ``uv run smpy openapi export``).

``gen-types`` (#504) turns each module's slice of the same schema into
``<package>/pages/api.generated.ts`` for the typed frontend client.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any

import typer

from simple_module_cli.openapi_types import (
    GenTypesError,
    filter_operations,
    generate,
    module_targets,
)

openapi_app = typer.Typer(help="OpenAPI schema tools.", no_args_is_help=True)

_ModuleOption = Annotated[
    list[str] | None,
    typer.Option("--module", help="Only this module (package or ModuleMeta name). Repeatable."),
]


def _project_root() -> Path:
    project_root = Path(os.environ.get("SM_PROJECT_ROOT") or Path.cwd())
    os.environ.setdefault("SM_PROJECT_ROOT", str(project_root))
    return project_root


def _build_app(project_root: Path) -> Any:
    """The host app, built in process; never serves a request."""
    try:
        from simple_module_core.dotenv import load_dotenv_into_environ
        from simple_module_hosting import create_app, merge_host_settings
        from simple_module_hosting._preapp_config import load_host_overrides
        from simple_module_hosting.bootstrap_settings import BootstrapSettings
    except ImportError:
        typer.echo(
            "error: simple_module_hosting is not installed — run this from a host "
            "project (`uv run smpy openapi ...`).",
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
    return create_app(merge_host_settings(strict=False))


@openapi_app.command("export")
def export(
    out: Annotated[Path, typer.Option("--out", help="File to write.")] = Path("openapi.json"),
    module: _ModuleOption = None,
) -> None:
    """Write the host's OpenAPI document (``/api/**`` only) to ``--out``."""
    schema = _build_app(_project_root()).openapi()
    if module:
        schema = filter_operations(schema, module)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    typer.echo(f"wrote {out} ({len(schema.get('paths', {}))} paths)")


@openapi_app.command("gen-types")
def gen_types(module: _ModuleOption = None) -> None:
    """Write ``<package>/pages/api.generated.ts`` for modules under this project.

    Without ``--module``: every module that already has the file. Needs Node
    (``npx``) unless ``openapi-typescript`` is installed in the project.
    """
    project_root = _project_root()
    app = _build_app(project_root)
    try:
        targets = module_targets(app.state.sm.modules, project_root, module or [])
        results = generate(app.openapi(), targets, project_root)
    except GenTypesError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    if not results:
        typer.echo("no module has pages/api.generated.ts; pass --module to start one")
    for target, changed, untyped in results:
        state = "wrote" if changed else "unchanged"
        typer.echo(f"{state} {target.output.resolve().relative_to(project_root.resolve())}")
        for op in untyped:
            typer.echo(f"  untyped response: {op} (add response_model=)", err=True)
