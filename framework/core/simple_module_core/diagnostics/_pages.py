"""SM003/SM004 page-vs-render diagnostics for Inertia view modules."""

from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel
from simple_module_core.modules._module_conventions import get_module_package_name

if TYPE_CHECKING:
    from simple_module_core.modules.module import ModuleBase


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


def _imported_str_consts(
    tree: ast.Module, package: str, modules: dict[str, dict[str, str]]
) -> dict[str, str]:
    """Bind imported names and module attributes using only scanned source."""
    imported: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                prefix = alias.asname or alias.name
                imported.update(
                    {f"{prefix}.{k}": v for k, v in modules.get(alias.name, {}).items()}
                )
        elif isinstance(node, ast.ImportFrom):
            try:
                name = resolve_name("." * node.level + (node.module or ""), package)
            except (ImportError, ValueError):
                continue
            for alias in node.names:
                bound = alias.asname or alias.name
                if alias.name in modules.get(name, {}):
                    imported[bound] = modules[name][alias.name]
                else:
                    imported.update(
                        {
                            f"{bound}.{k}": v
                            for k, v in modules.get(f"{name}.{alias.name}", {}).items()
                        }
                    )
    return imported


def _iter_render_components(tree: ast.Module, consts: dict[str, str]) -> list[str | None]:
    """Read render targets; ``None`` records a target that cannot be resolved."""
    found: list[str | None] = []
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
        elif isinstance(first, (ast.Name, ast.Attribute)):
            found.append(consts.get(ast.unparse(first)))
        else:
            found.append(None)
    return found


#: A ``*.test.tsx``/``*.spec.tsx`` beside a page is a test, not a page —
#: mirrors ``simple_module_hosting.frontend.page_globs.TEST_FILE_SUFFIXES``, which
#: excludes the same files from the Vite glob. Duplicated rather than
#: imported: ``simple_module_hosting`` depends on ``simple_module_core``,
#: not the other way around, so importing it here would invert the package
#: layering.
_TEST_FILE_SUFFIXES = (".test.tsx", ".spec.tsx")


def collect_tsx_pages(pages_dir: Path) -> set[str]:
    """Collect .tsx page identifiers relative to pages_dir, without extension.

    Nested files are represented with forward slashes so the set compares
    directly against inertia.render("Module/Sub/Page") keys. Subdirectories
    whose names start with a lowercase letter (``components/``, ``hooks/``,
    ...) are treated as helper folders, not Inertia page roots, matching the
    PascalCase convention Inertia uses. Files ending in ``.test.tsx`` or
    ``.spec.tsx`` are colocated tests, not pages, and are excluded the same
    way the Vite glob excludes them — otherwise a colocated test with no
    matching ``inertia.render()`` call is flagged as an SM003 orphan page.
    """
    pages: set[str] = set()
    for f in pages_dir.rglob("*.tsx"):
        if f.name.endswith(_TEST_FILE_SUFFIXES):
            continue
        rel = f.relative_to(pages_dir)
        if any(part[:1].islower() for part in rel.parts[:-1]):
            continue
        pages.add(rel.with_suffix("").as_posix())
    return pages


def find_render_calls(mod: ModuleBase, src_dir: Path) -> tuple[set[str], bool]:
    """Find rendered pages and whether any target is unresolved.

    Cache each source tree and its constants for this scan. Imports only bind
    constants from this package; no imported code is executed.
    """
    root_package = get_module_package_name(mod)
    trees: dict[str, ast.Module] = {}
    packages: dict[str, str] = {}
    for py_file in src_dir.rglob("*.py"):
        if not py_file.resolve().is_relative_to(src_dir.resolve()):
            continue
        parts = py_file.relative_to(src_dir).with_suffix("").parts
        package = ".".join((root_package, *parts[:-1]))
        name = package if parts[-1] == "__init__" else f"{package}.{parts[-1]}"
        try:
            trees[name] = ast.parse(py_file.read_text(), filename=str(py_file))
            packages[name] = package
        except (SyntaxError, OSError, UnicodeError):
            continue
    modules = {name: _module_level_str_consts(tree) for name, tree in trees.items()}
    for name, tree in trees.items():
        consts = modules[name]
        while True:
            resolved = _resolve_fstring_consts(tree, consts)
            new = {k: v for k, v in resolved.items() if k not in consts}
            if not new:
                break
            consts.update(new)

    prefix = f"{mod.meta.name}/"
    rendered: set[str] = set()
    unresolved = False
    for name, tree in trees.items():
        consts = {**_imported_str_consts(tree, packages[name], modules), **modules[name]}
        for component in _iter_render_components(tree, consts):
            if component is None:
                unresolved = True
            elif component.startswith(prefix):
                rendered.add(component[len(prefix) :])
    return rendered, unresolved


def check_pages(
    mod: ModuleBase,
    src_dir: Path,
    rendered_pages: set[str],
    *,
    unresolved_renders: bool = False,
) -> list[Diagnostic]:
    """Diff .tsx pages against rendered_pages — emits SM003 + SM004 in one pass."""
    pages_dir = src_dir / "pages"
    tsx_pages = collect_tsx_pages(pages_dir)
    diags: list[Diagnostic] = [
        Diagnostic(
            level=DiagnosticLevel.INFO if unresolved_renders else DiagnosticLevel.WARNING,
            code="SM003",
            message=(
                f"Page '{name}.tsx' exists but no matching inertia.render() found"
                + (" (some render targets could not be resolved)" if unresolved_renders else "")
            ),
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
