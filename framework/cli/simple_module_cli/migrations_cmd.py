"""Create schema revisions and prepare frozen upgrades in the host's Alembic graph."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from simple_module_cli._add_install import _default_exec_runner
from simple_module_cli._migration_support import (
    NO_ALEMBIC_CONFIG,
    data_upgrade_entry_points,
    resolve_alembic_ini,
    resolve_project_root,
)
from simple_module_cli.case import to_snake_case

migrations_app = typer.Typer(help="Create and prepare host-owned Alembic revisions.")


@migrations_app.command("new")
def new_revision(
    module: Annotated[str, typer.Argument(help="Module branch label (e.g. orders).")],
    message: Annotated[str, typer.Option("--message", "-m", help="Revision description.")],
    config: Annotated[Path | None, typer.Option("--config", help="Host alembic.ini.")] = None,
) -> None:
    """Autogenerate on a module's head, or start its first labelled root."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.util.exc import CommandError
    except ImportError as exc:
        raise typer.BadParameter("Run this command in a host with Alembic installed") from exc

    label = to_snake_case(module)
    if not re.fullmatch(r"[a-z][a-z0-9_]*", label):
        raise typer.BadParameter("Module label must be a Python-style module name")
    ini = resolve_alembic_ini(override=config)
    if ini is None:
        raise typer.BadParameter(NO_ALEMBIC_CONFIG)
    ini = ini.resolve()
    try:
        script = ScriptDirectory.from_config(Config(str(ini)))
        labels = {name for rev in script.walk_revisions() for name in rev.branch_labels}
        if label in labels:
            script.get_revision(f"{label}@head")  # refuse ambiguous module heads
    except CommandError as exc:
        raise typer.BadParameter(str(exc)) from exc
    root = resolve_project_root().resolve()
    cmd = ["uv", "run"]
    if ini.parent == root / "host":
        cmd.extend(["--project", str(ini.parent)])
    cmd.extend(["alembic", "-c", str(ini), "revision", "--autogenerate", "-m", message])
    cmd.extend(
        ["--head", f"{label}@head"]
        if label in labels
        else ["--head", "base", "--branch-label", label]
    )
    raise typer.Exit(_default_exec_runner(cmd, root))


@migrations_app.command("prepare")
def prepare(
    upgrade_id: Annotated[str, typer.Argument(help="Stable framework upgrade id.")],
    head: Annotated[str, typer.Option("--head", help="Explicit host head or label@head.")],
    config: Annotated[Path | None, typer.Option("--config", help="Host alembic.ini.")] = None,
) -> None:
    """Write a self-contained revision; never connect to or migrate the database."""
    entries = data_upgrade_entry_points()
    recipes = entries.select(name=upgrade_id)
    if not recipes:
        available = ", ".join(sorted(entries.names)) or "none"
        raise typer.BadParameter(f"Unknown upgrade {upgrade_id!r}. Available upgrades: {available}")
    if len(recipes) > 1:
        providers = ", ".join(
            f"{entry.dist.name} ({entry.value})" if entry.dist else entry.value for entry in recipes
        )
        raise typer.BadParameter(
            f"Multiple installed recipes for upgrade {upgrade_id!r}: {providers}"
        )
    try:
        from alembic.config import Config
        from alembic.script import Script, ScriptDirectory
        from alembic.util.exc import CommandError
    except ImportError as exc:
        raise typer.BadParameter(
            "Run this command in the host environment with Alembic installed"
        ) from exc

    ini = resolve_alembic_ini(override=config)
    if ini is None:
        raise typer.BadParameter(
            f"Alembic config not found: {config}" if config else NO_ALEMBIC_CONFIG
        )
    try:
        script = ScriptDirectory.from_config(Config(str(ini)))
        parent = script.get_revision(head)
        if parent is None or not parent.is_head:
            raise typer.BadParameter("--head must resolve to one existing host head")
        existing = {name for rev in script.walk_revisions() for name in rev.branch_labels}
    except CommandError as exc:
        raise typer.BadParameter(str(exc)) from exc

    parent_path = Path(parent.path)
    # Alembic resolves file symlinks before exposing parent.path.
    if parent_path.suffix != ".py" or not any(
        Path(candidate).resolve() == parent_path and not Path(candidate).is_symlink()
        for location in script._version_locations
        for candidate in Script._list_py_dir(script, Path(location))
    ):
        raise typer.BadParameter("--head must be a source revision in a scanned version directory")

    # Frozen source is copied, so future package changes cannot change this revision.
    try:
        recipe = next(iter(recipes)).load()()
        if not isinstance(recipe, tuple) or len(recipe) != 2:
            raise ValueError("expected a (branch label, Python source) tuple")
        label, source = recipe
        if not isinstance(label, str) or not label.strip() or not isinstance(source, str):
            raise ValueError("expected a nonempty branch label and Python source")
    except Exception as exc:
        raise typer.BadParameter(f"Could not load recipe for {upgrade_id!r}: {exc}") from exc
    revision = uuid4().hex[:12]
    branch_labels = None if label in existing else (label,)
    identifiers = (
        f"\nrevision = {revision!r}\ndown_revision = {parent.revision!r}\n"
        f"branch_labels = {branch_labels!r}\ndepends_on = None\n"
    )
    slug = re.sub(r"[^\w-]", "_", upgrade_id)
    path = parent_path.with_name(f"{revision}_{slug}.py")
    source += identifiers
    try:
        tree = ast.parse(source.encode("utf-8"), filename=str(path))
        compile(tree, str(path), "exec")
    except (SyntaxError, ValueError) as exc:
        raise typer.BadParameter(f"Invalid revision from recipe {upgrade_id!r}: {exc}") from exc
    functions = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            args = node.args
            if len(args.defaults) == len(args.posonlyargs) + len(args.args) and all(
                default is not None for default in args.kw_defaults
            ):
                functions.add(node.name)
    if not {"upgrade", "downgrade"} <= functions:
        raise typer.BadParameter(
            f"Recipe {upgrade_id!r} needs upgrade() and downgrade() with no required arguments"
        )
    with path.open("x", encoding="utf-8") as output:
        output.write(source)
    typer.echo(f"Prepared {upgrade_id}: {path}. Review it, then run alembic upgrade heads.")
