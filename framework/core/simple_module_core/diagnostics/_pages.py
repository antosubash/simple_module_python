"""SM003/SM004 page-vs-render diagnostics for Inertia view modules."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase


def _module_level_str_consts(tree: ast.Module) -> dict[str, str]:
    """Return ``{name: literal}`` for top-level ``NAME = "string"`` assignments."""
    return {
        s.targets[0].id: s.value.value
        for s in tree.body
        if isinstance(s, ast.Assign)
        and len(s.targets) == 1
        and isinstance(s.targets[0], ast.Name)
        and isinstance(s.value, ast.Constant)
        and isinstance(s.value.value, str)
    }


def _iter_render_components(tree: ast.Module, consts: dict[str, str]) -> list[str]:
    """Yield ``X.render(component, ...)`` first-arg values, resolving Name references."""
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


def collect_tsx_pages(pages_dir: Path) -> set[str]:
    """Collect .tsx page identifiers relative to pages_dir, without extension.

    Nested files are represented with forward slashes so the set compares
    directly against inertia.render("Module/Sub/Page") keys. Subdirectories
    whose names start with a lowercase letter (``components/``, ``hooks/``,
    ...) are treated as helper folders, not Inertia page roots, matching the
    PascalCase convention Inertia uses.
    """
    pages: set[str] = set()
    for f in pages_dir.rglob("*.tsx"):
        rel = f.relative_to(pages_dir)
        if any(part[:1].islower() for part in rel.parts[:-1]):
            continue
        pages.add(rel.with_suffix("").as_posix())
    return pages


def find_render_calls(mod: ModuleBase, src_dir: Path) -> set[str]:
    """Find inertia.render("Module/Page") calls in this module's source tree.

    Resolves ``inertia.render(NAME)`` where ``NAME`` is a string constant
    defined at module scope in any sibling .py file (e.g. ``constants.py``).
    Each .py file is parsed once: a first pass collects every module-level
    string const, a second pass walks render calls against the merged map.
    """
    trees: list[ast.Module] = []
    for py_file in src_dir.rglob("*.py"):
        try:
            trees.append(ast.parse(py_file.read_text(), filename=str(py_file)))
        except (SyntaxError, OSError):
            continue
    consts: dict[str, str] = {}
    for tree in trees:
        consts.update(_module_level_str_consts(tree))

    prefix = f"{mod.meta.name}/"
    rendered: set[str] = set()
    for tree in trees:
        for component in _iter_render_components(tree, consts):
            if component.startswith(prefix):
                rendered.add(component[len(prefix) :])
    return rendered


def check_pages(
    mod: ModuleBase,
    src_dir: Path,
    rendered_pages: set[str],
) -> list[Diagnostic]:
    """Diff .tsx pages against rendered_pages — emits SM003 + SM004 in one pass."""
    pages_dir = src_dir / "pages"
    tsx_pages = collect_tsx_pages(pages_dir)
    diags: list[Diagnostic] = [
        Diagnostic(
            level=DiagnosticLevel.WARNING,
            code="SM003",
            message=f"Page '{name}.tsx' exists but no matching inertia.render() found",
            module_name=mod.meta.name,
            file=str(pages_dir / f"{name}.tsx"),
            suggestion=f'Add inertia.render("{mod.meta.name}/{name}", ...) in a view endpoint',
        )
        for name in tsx_pages - rendered_pages
    ]
    diags.extend(
        Diagnostic(
            level=DiagnosticLevel.WARNING,
            code="SM004",
            message=f'inertia.render("{mod.meta.name}/{name}") but no {name}.tsx exists',
            module_name=mod.meta.name,
            suggestion=f"Create {pages_dir / f'{name}.tsx'}",
        )
        for name in rendered_pages - tsx_pages
    )
    return diags
