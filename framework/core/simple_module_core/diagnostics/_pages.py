"""SM003/SM004 page-vs-render diagnostics for Inertia view modules."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase


def _iter_render_components(
    tree: ast.Module, extra_consts: dict[str, str] | None = None
) -> list[str]:
    """Yield ``X.render(component, ...)`` first-arg values, resolving Name constants.

    ``extra_consts`` lets the caller supply a registry of names defined in
    sibling modules (e.g. ``constants.py``) so that
    ``inertia.render(PAGE_BROWSE, ...)`` resolves when ``PAGE_BROWSE`` is
    imported from another file.
    """
    consts: dict[str, str] = dict(extra_consts or {})
    consts.update(
        {
            s.targets[0].id: s.value.value
            for s in tree.body
            if isinstance(s, ast.Assign)
            and len(s.targets) == 1
            and isinstance(s.targets[0], ast.Name)
            and isinstance(s.value, ast.Constant)
            and isinstance(s.value.value, str)
        }
    )
    found: list[str] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "render"
            and node.args
        ):
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found.append(first.value)
        elif isinstance(first, ast.Name) and first.id in consts:
            found.append(consts[first.id])
    return found


def _collect_module_string_consts(src_dir: Path) -> dict[str, str]:
    """Collect module-level ``NAME = "literal"`` assignments across all .py files.

    Last definition wins on collisions. Used to resolve ``inertia.render(NAME)``
    when ``NAME`` is imported from a sibling file like ``constants.py``.
    """
    registry: dict[str, str] = {}
    for py_file in src_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
        except (SyntaxError, OSError):
            continue
        for stmt in tree.body:
            if not (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                continue
            registry[stmt.targets[0].id] = stmt.value.value
    return registry


def collect_tsx_pages(pages_dir: Path) -> set[str]:
    """Collect .tsx page identifiers relative to pages_dir, without extension.

    Nested files are represented with forward slashes so the set compares
    directly against inertia.render("Module/Sub/Page") keys. Subdirectories
    whose names start with a lowercase letter (e.g. ``components/``,
    ``hooks/``) are treated as helper folders — not Inertia page roots —
    and skipped, matching the PascalCase convention Inertia uses.
    """
    if not pages_dir.exists():
        return set()
    pages: set[str] = set()
    for f in pages_dir.rglob("*.tsx"):
        rel = f.relative_to(pages_dir)
        if any(part[:1].islower() for part in rel.parts[:-1]):
            continue
        pages.add(rel.with_suffix("").as_posix())
    return pages


def find_render_calls(mod: ModuleBase, src_dir: Path) -> set[str]:
    """Find inertia.render("Module/Page") calls, resolving module-level string consts."""
    rendered: set[str] = set()
    prefix = f"{mod.meta.name}/"
    cross_file_consts = _collect_module_string_consts(src_dir)
    for py_file in src_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
        except SyntaxError:
            continue
        for component in _iter_render_components(tree, cross_file_consts):
            if component.startswith(prefix):
                rendered.add(component[len(prefix) :])
    return rendered


def check_orphan_pages(
    mod: ModuleBase,
    src_dir: Path,
    rendered_pages: set[str],
) -> list[Diagnostic]:
    """Find .tsx pages that aren't referenced by any inertia.render() call."""
    pages_dir = src_dir / "pages"
    tsx_pages = collect_tsx_pages(pages_dir)
    orphans = tsx_pages - rendered_pages

    return [
        Diagnostic(
            level=DiagnosticLevel.WARNING,
            code="SM003",
            message=f"Page '{name}.tsx' exists but no matching inertia.render() found",
            module_name=mod.meta.name,
            file=str(pages_dir / f"{name}.tsx"),
            suggestion=f'Add inertia.render("{mod.meta.name}/{name}", ...) in a view endpoint',
        )
        for name in orphans
    ]


def check_phantom_renders(
    mod: ModuleBase,
    src_dir: Path,
    rendered_pages: set[str],
) -> list[Diagnostic]:
    """Find inertia.render() calls that reference non-existent pages."""
    pages_dir = src_dir / "pages"
    tsx_pages = collect_tsx_pages(pages_dir)
    phantoms = rendered_pages - tsx_pages

    return [
        Diagnostic(
            level=DiagnosticLevel.WARNING,
            code="SM004",
            message=f'inertia.render("{mod.meta.name}/{name}") but no {name}.tsx exists',
            module_name=mod.meta.name,
            suggestion=f"Create {pages_dir / f'{name}.tsx'}",
        )
        for name in phantoms
    ]
