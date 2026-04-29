"""``sm skills`` — install or update agent skill packs in a target project.

Bundles the SKILL.md packs shipped under ``simple_module_cli/skills/`` and
materialises them into a project directory (default ``.claude/skills``) so any
agent that reads the [Agent Skills format](https://agentskills.io/specification)
can pick them up.

Three subcommands:

* ``sm skills list``    — show every bundled skill and its description.
* ``sm skills add``     — copy (or symlink) skills into the destination.
* ``sm skills update``  — re-copy skills that are already installed at the
                          destination, overwriting them.
"""

from __future__ import annotations

import importlib.resources
import re
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated

import typer

__all__ = ["app", "install_skill", "iter_bundled_skills"]

app = typer.Typer(
    help="Install agent skills (Claude Code / Agent Skills format) into a project.",
    no_args_is_help=True,
)

_DEFAULT_PROJECT_DIR = Path(".claude") / "skills"
_GLOBAL_DIR = Path.home() / ".claude" / "skills"
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def _bundled_skills_root() -> Path:
    """Path to the ``skills/`` directory shipped inside the wheel.

    Resolved via ``importlib.resources`` so editable installs and wheels both
    work; tests can monkey-patch this to point at a fixture directory.
    """
    return Path(str(importlib.resources.files("simple_module_cli") / "skills"))


def iter_bundled_skills(root: Path | None = None) -> list[Path]:
    """Return every bundled skill directory (one with a SKILL.md), sorted."""
    base = root if root is not None else _bundled_skills_root()
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())


def _read_description(skill_dir: Path) -> str:
    """Pull the ``description:`` field out of a SKILL.md's YAML frontmatter."""
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return ""
    body = match.group(1)
    out_lines: list[str] = []
    in_desc = False
    for line in body.splitlines():
        if line.startswith("description:"):
            in_desc = True
            out_lines.append(line.split(":", 1)[1].strip())
            continue
        if in_desc:
            if line and not line[0].isspace() and ":" in line:
                break
            out_lines.append(line.strip())
    return " ".join(s for s in out_lines if s).strip()


def _resolve_dest(dest: Path | None, global_: bool) -> Path:
    if dest is not None:
        return dest
    if global_:
        return _GLOBAL_DIR
    return Path.cwd() / _DEFAULT_PROJECT_DIR


def _select(names: Iterable[str], available: list[Path]) -> list[Path]:
    by_name = {p.name: p for p in available}
    requested = [n for n in names if n]
    if not requested:
        return list(available)
    unknown = [n for n in requested if n not in by_name]
    if unknown:
        typer.echo(f"ERROR: unknown skill(s): {', '.join(unknown)}", err=True)
        typer.echo(f"Available: {', '.join(sorted(by_name))}", err=True)
        raise typer.Exit(code=1)
    return [by_name[n] for n in requested]


def install_skill(
    src: Path,
    dest_root: Path,
    *,
    force: bool,
    symlink: bool,
) -> tuple[str, Path]:
    """Copy or symlink one skill directory into ``dest_root/<skill_name>/``.

    Returns ``(action, target_path)`` where action is one of
    ``"wrote"``, ``"updated"``, or ``"skipped"``.
    """
    target = dest_root / src.name
    if target.exists() or target.is_symlink():
        if not force:
            return ("skipped", target)
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
        action = "updated"
    else:
        action = "wrote"
    target.parent.mkdir(parents=True, exist_ok=True)
    if symlink:
        target.symlink_to(src.resolve(), target_is_directory=True)
    else:
        shutil.copytree(src, target)
    return (action, target)


@app.command("list")
def list_skills() -> None:
    """List every bundled skill and its trigger description."""
    skills = iter_bundled_skills()
    if not skills:
        typer.echo("(no skills bundled)")
        return
    width = max(len(s.name) for s in skills)
    for skill in skills:
        desc = _read_description(skill)
        typer.echo(f"  {skill.name.ljust(width)}  {desc}")


@app.command("add")
def add_skills(
    names: Annotated[
        list[str] | None,
        typer.Argument(help="Skill names to install. Empty = install every bundled skill."),
    ] = None,
    dest: Annotated[
        Path | None,
        typer.Option("--dest", help="Target directory. Defaults to ./.claude/skills."),
    ] = None,
    global_: Annotated[
        bool,
        typer.Option("--global", "-g", help="Install into ~/.claude/skills (machine-wide)."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing skill directories."),
    ] = False,
    symlink: Annotated[
        bool,
        typer.Option(
            "--symlink",
            help="Symlink to the bundled source instead of copying. "
            "Useful when developing the skills in-tree.",
        ),
    ] = False,
) -> None:
    """Install bundled simple_module skills into a project."""
    available = iter_bundled_skills()
    if not available:
        typer.echo("ERROR: no bundled skills found in this CLI install.", err=True)
        raise typer.Exit(code=1)

    selected = _select(names or [], available)
    target_root = _resolve_dest(dest, global_)
    target_root.mkdir(parents=True, exist_ok=True)

    counts = {"wrote": 0, "updated": 0, "skipped": 0}
    for src in selected:
        action, target = install_skill(src, target_root, force=force, symlink=symlink)
        counts[action] += 1
        typer.echo(f"  {action:8} {src.name} -> {target}")

    typer.echo(
        f"\nDone. wrote={counts['wrote']} updated={counts['updated']} "
        f"skipped={counts['skipped']} (target: {target_root})"
    )
    if counts["skipped"]:
        typer.echo("Pass --force to overwrite skipped skills.")


@app.command("update")
def update_skills(
    names: Annotated[
        list[str] | None,
        typer.Argument(help="Skill names to update. Empty = update every skill already installed."),
    ] = None,
    dest: Annotated[
        Path | None,
        typer.Option("--dest", help="Target directory. Defaults to ./.claude/skills."),
    ] = None,
    global_: Annotated[
        bool,
        typer.Option("--global", "-g", help="Update ~/.claude/skills (machine-wide)."),
    ] = False,
    symlink: Annotated[
        bool,
        typer.Option(
            "--symlink",
            help="Symlink to the bundled source instead of copying.",
        ),
    ] = False,
) -> None:
    """Re-copy bundled skills, overwriting existing targets.

    With no arguments: only updates skills already present in the destination
    (so you can re-pull the latest copies without re-deciding which ones you want).
    """
    available = iter_bundled_skills()
    if not available:
        typer.echo("ERROR: no bundled skills found in this CLI install.", err=True)
        raise typer.Exit(code=1)

    target_root = _resolve_dest(dest, global_)
    requested = list(names or [])
    if requested:
        selected = _select(requested, available)
    else:
        if not target_root.is_dir():
            typer.echo(f"Nothing to update — {target_root} does not exist.")
            return
        installed = {p.name for p in target_root.iterdir() if p.is_dir() or p.is_symlink()}
        selected = [s for s in available if s.name in installed]
        if not selected:
            typer.echo(f"Nothing to update — no installed skills found at {target_root}.")
            return

    target_root.mkdir(parents=True, exist_ok=True)
    for src in selected:
        action, target = install_skill(src, target_root, force=True, symlink=symlink)
        typer.echo(f"  {action:8} {src.name} -> {target}")
    typer.echo(f"\nDone. Updated {len(selected)} skill(s) at {target_root}.")
