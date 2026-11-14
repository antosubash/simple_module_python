"""Root `smpy` Typer app — scaffolders + plugin mount.

Built-in commands:
  smpy new
  smpy add
  smpy update
  smpy create-host
  smpy create-module
  smpy skills add / list / update

Plugins discovered via the ``simple_module_cli.cli_plugins`` entry-point
group are mounted as named subgroups (e.g. ``smpy host gen-pages``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from simple_module_cli._project_cli_check import (
    app_framework_pin,
    running_cli,
    warn_if_not_the_apps_cli,
)
from simple_module_cli.add_cmd import add_module, run_add
from simple_module_cli.case import to_kebab_case
from simple_module_cli.docker_cmd import docker_app
from simple_module_cli.migrations_cmd import migrations_app
from simple_module_cli.module_cmd import module_app
from simple_module_cli.new import new_project
from simple_module_cli.openapi_cmd import openapi_app
from simple_module_cli.package_update import package_update
from simple_module_cli.plugins import discover_and_mount
from simple_module_cli.scaffolding import create_host as _create_host
from simple_module_cli.scaffolding import create_module as _create_module
from simple_module_cli.scaffolding import is_inside_existing_repo, resolve_framework_version
from simple_module_cli.skills_cmd import app as skills_app
from simple_module_cli.update_cmd import update_modules
from simple_module_cli.uv_workspace import find_workspace_root, is_workspace_member

app = typer.Typer(
    help="SimpleModule developer CLI.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _check_project_cli(ctx: typer.Context) -> None:
    warn_if_not_the_apps_cli(ctx.invoked_subcommand, resolve_framework_version(), Path.cwd())


app.command("new")(new_project)
app.command("add")(add_module)
app.command("update")(update_modules)
app.command("package-update")(package_update)
app.add_typer(docker_app, name="docker")
app.add_typer(skills_app, name="skills")
app.add_typer(module_app, name="module")
app.add_typer(openapi_app, name="openapi")
app.add_typer(migrations_app, name="migrations")


@app.command("doctor")
def doctor() -> None:
    """Check installed modules and their database compatibility."""
    try:
        from simple_module_core.__main__ import main as run_doctor
    except ImportError:
        # The CLI installs on its own (to scaffold); doctor needs a project's framework.
        if app_framework_pin(Path.cwd()) is None:
            message = "smpy doctor needs simple_module_core; run it inside a project."
        else:
            # Inside an app, this is a global smpy outside the app's venv (GH #929).
            message = (
                f"this smpy ({running_cli()}) is not installed in this project's venv, "
                "so it cannot see the app's modules. Run `uv sync --all-packages`, "
                "then `uv run smpy doctor`."
            )
        typer.echo(f"ERROR: {message}", err=True)
        raise typer.Exit(1) from None

    raise typer.Exit(run_doctor())


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
    git_module: Annotated[
        list[str] | None,
        typer.Option(
            "--git-module",
            help="git+URL[@ref][#subdirectory=dir] module source; repeatable. "
            "Multi-module repos need an explicit #subdirectory here.",
        ),
    ] = None,
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

    # create-host is non-interactive: multi-module repos need #subdirectory.
    for spec in git_module or []:
        run_add(spec, pyproject=target / "pyproject.toml", no_sync=True, assume_yes=True)

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


def _app_add_command(target: Path) -> str | None:
    """``smpy add …`` wiring a module into its app's host, or None outside an app (GH #442)."""
    root = find_workspace_root(target.parent)
    if root is None:
        return None
    host = root / "host"
    if not (host / "pyproject.toml").is_file() or not is_workspace_member(host, target):
        return None
    rel = os.path.relpath(target.resolve(), host.resolve())
    if not rel.startswith("."):
        rel = f"./{rel}"  # parse_add_spec reads a bare "a/b" as a PyPI requirement
    # The steps are printed "from the app root", so name the host relative to it.
    host_arg = host.resolve().relative_to(root.resolve()).as_posix()
    # `uv run`: after `uvx … smpy new`, `smpy` itself is not on PATH (GH #931).
    return f"uv run smpy add {rel} --path {host_arg}"


def _echo_app_next_steps(add_command: str, slug: str) -> None:
    """The module lives in an app's workspace: wire it in with the app's own commands.

    Never ``uv sync`` inside the module: that syncs the module alone and
    uninstalls the rest of the app from the shared venv (GH #916).
    """
    typer.echo("\nNext steps (from the app root):")
    typer.echo(f"  {add_command}   # adds it as {{ workspace = true }}")
    typer.echo("  make install   # links its pages (npm) and generates its i18n keys")
    typer.echo(f'  make migration msg="add {slug}"')
    typer.echo("  make migrate")
    typer.echo("  make test")
    typer.echo("Then restart `make dev`: modules are discovered at start-up, not on reload.")


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
    add_command = _app_add_command(target)
    if add_command is not None:
        _echo_app_next_steps(add_command, slug)
    else:
        typer.echo("\nNext steps:")
        typer.echo(f"  cd {target}")
        typer.echo("  uv sync --extra dev")
        typer.echo("  uv run pytest")
        typer.echo("  npm install")
        typer.echo("  npm run typecheck")
        typer.echo("  uv run smpy module verify")
    typer.echo(
        "\nThe pages ship sample API types (pages/api.generated.ts). Once the host serves "
        "the module, refresh them after any endpoint change:\n"
        f"  uv run smpy openapi gen-types --module {package}"
    )


discover_and_mount(app)


def main() -> None:
    """Entry point for the `smpy` console script."""
    app()


if __name__ == "__main__":
    main()
