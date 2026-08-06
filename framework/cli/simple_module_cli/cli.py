"""Root `smpy` Typer app — scaffolders + plugin mount.

Built-in commands:
  smpy new
  smpy create-host
  smpy create-module
  smpy skills add / list / update

Plugins discovered via the ``simple_module_cli.cli_plugins`` entry-point
group are mounted as named subgroups (e.g. ``smpy host gen-pages``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from simple_module_cli.case import to_kebab_case
from simple_module_cli.new import new_project
from simple_module_cli.package_update import package_update
from simple_module_cli.plugins import discover_and_mount
from simple_module_cli.scaffolding import create_host as _create_host
from simple_module_cli.scaffolding import create_module as _create_module
from simple_module_cli.scaffolding import is_inside_existing_repo, resolve_framework_version
from simple_module_cli.skills_cmd import app as skills_app

app = typer.Typer(
    help="SimpleModule developer CLI.",
    no_args_is_help=True,
    add_completion=False,
)

app.command("new")(new_project)
app.command("package-update")(package_update)
app.add_typer(skills_app, name="skills")


@app.command("create-host")
def create_host(
    name: Annotated[str, typer.Argument(help="Host project name.")],
    dest: Annotated[
        Path | None,
        typer.Option("--dest", help="Destination directory. Defaults to ./<name>."),
    ] = None,
    modules: Annotated[
        str,
        typer.Option(
            "--with",
            help="Comma-separated module names to declare as deps (e.g. Auth,Dashboard).",
        ),
    ] = "",
) -> None:
    """Scaffold a new SimpleModule host project at ./<NAME>."""
    target = dest or Path.cwd() / name
    selected = [m.strip() for m in modules.split(",") if m.strip()]
    try:
        # Pin the host's framework + module deps to the installed framework
        # version so the generated host's first `uv sync` resolves (the
        # template's >=1.0,<2.0 / >=0.1,<1.0 ranges don't exist pre-1.0). The
        # workspace `smpy new` path rewrites these via _rewrite_pyproject, but
        # standalone create-host never did — see GH #206.
        _create_host(
            target,
            name=name,
            modules=selected,
            framework_version=resolve_framework_version(),
        )
    except FileExistsError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Created host '{name}' at {target}")
    if selected:
        typer.echo(f"Declared modules: {', '.join(selected)}")
    typer.echo("\nNext steps:")
    typer.echo(f"  cd {target}")
    typer.echo("  uv sync")
    typer.echo("  cp .env.example .env")
    typer.echo('  alembic revision --autogenerate -m "initial schema"')
    typer.echo("  alembic upgrade heads")
    typer.echo("  python main.py")


@app.command("create-module")
def create_module(
    name: Annotated[str, typer.Argument(help="Module name (any case).")],
    dest: Annotated[
        Path | None,
        typer.Option("--dest", help="Destination dir. Defaults to ./simple_module_<name>."),
    ] = None,
    standalone: Annotated[
        bool,
        typer.Option(
            "--standalone",
            help="Emit the module's own .github/ CI + PyPI publish workflows. "
            "By default they are omitted when the module lands inside an "
            "existing repo/host (nested workflows never run there).",
        ),
    ] = False,
) -> None:
    """Scaffold a publishable SimpleModule module package."""
    slug = to_kebab_case(name)
    package = slug.replace("-", "_")
    target = dest or Path.cwd() / f"simple_module_{package}"
    # An in-repo module (the documented modules/* layout) gets no .github/ and
    # keeps the workspace JS configs: nested workflows never run and publish.yml
    # is a PyPI footgun. --standalone forces the standalone layout for a module
    # that lives in its own repo. See GH #210.
    standalone_mode = standalone or not is_inside_existing_repo(target)
    try:
        # Pin framework deps to the installed framework version so the module
        # resolves against the app that created it (the template's >=1.0,<2.0
        # ranges don't exist on PyPI pre-1.0). See GH #195.
        _create_module(
            target,
            name=name,
            framework_version=resolve_framework_version(),
            standalone=standalone_mode,
        )
    except FileExistsError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Created module 'simple_module_{package}' at {target}")
    if not standalone_mode:
        typer.echo(
            "Skipped .github/ workflows: this module is inside an existing repo, "
            "where nested workflows never run. Use --standalone to emit them."
        )
    typer.echo("\nNext steps:")
    typer.echo(f"  cd {target}")
    typer.echo("  uv sync --extra dev")
    typer.echo("  uv run pytest")
    typer.echo("  npm install")
    typer.echo("  npm run typecheck")
    typer.echo("  uv run smpy module verify")


discover_and_mount(app)


def main() -> None:
    """Entry point for the `smpy` console script."""
    app()


if __name__ == "__main__":
    main()
