"""Structural diagnostics that validate discovered modules against invariants."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._coupling import check_framework_module_coupling
from simple_module_core.diagnostics._inertia_api import check_inertia_api_calls
from simple_module_core.diagnostics._js_workspace import check_js_workspace_files
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


class ModuleDiagnostics:
    """Validates module structure and configuration."""

    def run(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        diagnostics.extend(self._check_duplicate_names(modules))
        diagnostics.extend(self._check_schema_conflicts(modules))
        diagnostics.extend(self._check_empty_modules(modules))
        diagnostics.extend(self._check_missing_meta(modules))
        diagnostics.extend(self._check_views_without_menu(modules))
        diagnostics.extend(check_framework_module_coupling(modules))

        # File-based checks (need to find module source directories)
        for mod in modules:
            src_dir = self._find_source_dir(mod)
            if src_dir:
                rendered_pages = self._find_render_calls(mod, src_dir)
                diagnostics.extend(self._check_orphan_pages(mod, src_dir, rendered_pages))
                diagnostics.extend(self._check_phantom_renders(mod, src_dir, rendered_pages))
                diagnostics.extend(check_js_workspace_files(mod, src_dir))
                diagnostics.extend(check_inertia_api_calls(mod, src_dir))

        return diagnostics

    def _check_duplicate_names(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        seen: dict[str, str] = {}
        diags: list[Diagnostic] = []
        for mod in modules:
            name = mod.meta.name
            cls_name = type(mod).__qualname__
            if name in seen:
                diags.append(
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="SM008",
                        message=f"Duplicate module name '{name}' (also in {seen[name]})",
                        module_name=cls_name,
                        suggestion="Each module must have a unique meta.name",
                    )
                )
            seen[name] = cls_name
        return diags

    def _check_schema_conflicts(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        """Check for modules that would create conflicting DB schemas."""
        prefixes: dict[str, str] = {}
        diags: list[Diagnostic] = []
        for mod in modules:
            prefix = mod.meta.name.lower()
            if prefix in prefixes:
                diags.append(
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="SM008",
                        message=(
                            f"Schema/table prefix '{prefix}' conflicts "
                            f"with module '{prefixes[prefix]}'"
                        ),
                        module_name=mod.meta.name,
                        suggestion="Use unique module names to avoid DB schema conflicts",
                    )
                )
            prefixes[prefix] = mod.meta.name
        return diags

    def _check_empty_modules(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        diags: list[Diagnostic] = []
        for mod in modules:
            cls = type(mod)
            overridden = [
                name
                for name in (
                    "register_routes",
                    "register_menu_items",
                    "register_permissions",
                    "register_feature_flags",
                    "register_event_handlers",
                    "register_middleware",
                    "register_health_checks",
                    "register_exception_handlers",
                    "register_settings",
                    "template_dirs",
                    "static_mounts",
                    "locale_dirs",
                    "on_startup",
                    "on_shutdown",
                )
                if name in cls.__dict__
            ]
            if not overridden:
                diags.append(
                    Diagnostic(
                        level=DiagnosticLevel.INFO,
                        code="SM007",
                        message="Module exists but overrides no registration methods",
                        module_name=mod.meta.name,
                        suggestion="Override register_routes() or other methods to add functionality",  # noqa: E501
                    )
                )
        return diags

    def _check_views_without_menu(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        """Warn when a module ships view routes but is silently invisible.

        A module that overrides ``register_routes`` and declares a non-empty
        ``view_prefix`` produces user-facing pages. Without either
        ``register_menu_items`` (so admins can navigate to it from the sidebar)
        or ``register_permissions`` (so admins can see it in the role-permission
        editor), the module is silently invisible from the admin UI.

        Modules that surface their views as sub-pages of another module (e.g.
        deep-link edit forms reached from buttons elsewhere) typically register
        permissions even when they don't add a sidebar entry — that suffices to
        keep them discoverable through the role editor.
        """
        diags: list[Diagnostic] = []
        for mod in modules:
            cls = type(mod)
            meta = getattr(mod, "meta", None)
            if meta is None or not getattr(meta, "view_prefix", ""):
                continue
            if "register_routes" not in cls.__dict__:
                continue
            if "register_menu_items" in cls.__dict__:
                continue
            if "register_permissions" in cls.__dict__:
                continue
            diags.append(
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="SM019",
                    message=(
                        f"Module '{meta.name}' registers view routes "
                        f"(view_prefix={meta.view_prefix!r}) but no menu items "
                        "or permissions"
                    ),
                    module_name=meta.name,
                    suggestion=(
                        "Override register_menu_items() to surface this module "
                        "in the sidebar, register_permissions() to surface it in "
                        "the role editor, or clear view_prefix if it's API-only"
                    ),
                )
            )
        return diags

    def _check_missing_meta(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        diags: list[Diagnostic] = []
        for mod in modules:
            if not hasattr(mod, "meta"):
                diags.append(
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="SM001",
                        message="Module missing 'meta' class attribute",
                        module_name=type(mod).__qualname__,
                        suggestion="Add: meta = ModuleMeta(name='YourModule')",
                    )
                )
        return diags

    def _find_package_dir(self, package_name: str) -> Path | None:
        """Locate the source directory for a top-level package."""
        spec = importlib.util.find_spec(package_name)
        if spec and spec.submodule_search_locations:
            locations = list(spec.submodule_search_locations)
            if locations:
                return Path(locations[0])
        return None

    def _collect_tsx_pages(self, pages_dir: Path) -> set[str]:
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

    def _check_orphan_pages(
        self,
        mod: ModuleBase,
        src_dir: Path,
        rendered_pages: set[str],
    ) -> list[Diagnostic]:
        """Find .tsx pages that aren't referenced by any inertia.render() call."""
        pages_dir = src_dir / "pages"
        tsx_pages = self._collect_tsx_pages(pages_dir)
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

    def _check_phantom_renders(
        self,
        mod: ModuleBase,
        src_dir: Path,
        rendered_pages: set[str],
    ) -> list[Diagnostic]:
        """Find inertia.render() calls that reference non-existent pages."""
        pages_dir = src_dir / "pages"
        tsx_pages = self._collect_tsx_pages(pages_dir)
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

    def _find_render_calls(self, mod: ModuleBase, src_dir: Path) -> set[str]:
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

    def _find_source_dir(self, mod: ModuleBase) -> Path | None:
        """Locate the source directory for a module's package."""
        pkg_name = type(mod).__module__.rsplit(".", 1)[0]
        return self._find_package_dir(pkg_name)
