"""SM003/SM004 page-vs-render diagnostics for Inertia view modules."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase


def _assignment(s: ast.stmt) -> tuple[ast.Name, ast.expr] | None:
    """Return ``(target, value)`` for a single-target top-level assignment.

    Covers both ``NAME = ...`` and the annotated ``NAME: Final = ...`` form
    module constants are conventionally written in.
    """
    if isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name):
        return s.targets[0], s.value
    if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name) and s.value is not None:
        return s.target, s.value
    return None


def _module_level_str_consts(tree: ast.Module) -> dict[str, str]:
    """Return ``{name: literal}`` for top-level ``NAME = "string"`` assignments."""
    consts: dict[str, str] = {}
    for s in tree.body:
        assignment = _assignment(s)
        if assignment is None:
            continue
        target, value = assignment
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            consts[target.id] = value.value
    return consts


def _resolve_fstring_consts(tree: ast.Module, consts: dict[str, str]) -> dict[str, str]:
    """Resolve top-level ``NAME = f"{CONST}/lit"`` against already-known consts.

    Only plain interpolations of known string constants count — a conversion,
    format spec, or unknown name makes the value non-static, so it is skipped
    rather than guessed at.
    """
    resolved: dict[str, str] = {}
    for s in tree.body:
        assignment = _assignment(s)
        if assignment is None or not isinstance(assignment[1], ast.JoinedStr):
            continue
        target, value = assignment
        parts: list[str] = []
        for piece in value.values:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                parts.append(piece.value)
            elif (
                isinstance(piece, ast.FormattedValue)
                and isinstance(piece.value, ast.Name)
                and piece.value.id in consts
                and piece.conversion == -1
                and piece.format_spec is None
            ):
                parts.append(consts[piece.value.id])
            else:
                break
        else:
            resolved[target.id] = "".join(parts)
    return resolved


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
    # Then f-string constants built from the plain ones above
    # (``PAGE = f"{MODULE_NAME}/Browse"`` is the conventional shape). Repeat to
    # a fixed point so a chain — ``PREFIX = f"{NAME}/sub"`` then
    # ``PAGE = f"{PREFIX}/Browse"`` — resolves too; one pass would only learn
    # the first hop and report the page as an SM003 orphan.
    while True:
        resolved: dict[str, str] = {}
        for tree in trees:
            resolved.update(_resolve_fstring_consts(tree, consts))
        new = {k: v for k, v in resolved.items() if consts.get(k) != v}
        if not new:
            break
        consts.update(new)

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
