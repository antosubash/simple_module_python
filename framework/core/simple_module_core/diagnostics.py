"""Module diagnostics — validates structure and patterns at startup or via CLI."""

from __future__ import annotations

import ast
import importlib.util
import logging
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

logger = logging.getLogger(__name__)


class DiagnosticLevel(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Diagnostic:
    """A single diagnostic finding."""

    level: DiagnosticLevel
    code: str
    message: str
    module_name: str
    file: str | None = None
    suggestion: str | None = None

    def __str__(self) -> str:
        prefix = {"error": "\u2717", "warning": "\u26a0", "info": "\u2139"}[self.level]
        parts = [f"{prefix} {self.code} [{self.level.upper()}] {self.module_name}: {self.message}"]
        if self.file:
            parts.append(f"  \u21b3 {self.file}")
        if self.suggestion:
            parts.append(f"  \u21b3 Suggestion: {self.suggestion}")
        return "\n".join(parts)


class ModuleDiagnostics:
    """Validates module structure and configuration."""

    # Framework packages that must never import from plugin module packages.
    FRAMEWORK_PACKAGES = ("simple_module_core", "simple_module_hosting", "simple_module_db")

    def run(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        diagnostics.extend(self._check_duplicate_names(modules))
        diagnostics.extend(self._check_schema_conflicts(modules))
        diagnostics.extend(self._check_empty_modules(modules))
        diagnostics.extend(self._check_missing_meta(modules))
        diagnostics.extend(self._check_framework_module_coupling(modules))

        # File-based checks (need to find module source directories)
        for mod in modules:
            src_dir = self._find_source_dir(mod)
            if src_dir:
                rendered_pages = self._find_render_calls(mod, src_dir)
                diagnostics.extend(self._check_orphan_pages(mod, src_dir, rendered_pages))
                diagnostics.extend(self._check_phantom_renders(mod, src_dir, rendered_pages))

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

    def _check_framework_module_coupling(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        """Detect framework packages that directly import from plugin module packages.

        The framework (core, hosting, db) must never ``import`` from a
        discovered module's package (e.g. ``auth``, ``products``).
        All interaction should go through the ``ModuleBase`` lifecycle hooks.
        """
        # Collect top-level package names for every discovered module.
        module_packages: dict[str, str] = {}  # package -> module name
        for mod in modules:
            top_pkg = type(mod).__module__.split(".")[0]
            module_packages[top_pkg] = mod.meta.name

        if not module_packages:
            return []

        # Locate framework package source directories.
        framework_dirs: list[tuple[str, Path]] = []
        for fw_pkg in self.FRAMEWORK_PACKAGES:
            fw_dir = self._find_package_dir(fw_pkg)
            if fw_dir:
                framework_dirs.append((fw_pkg, fw_dir))

        diags: list[Diagnostic] = []
        for fw_pkg, fw_dir in framework_dirs:
            for py_file in fw_dir.rglob("*.py"):
                try:
                    tree = ast.parse(py_file.read_text(), filename=str(py_file))
                except SyntaxError:
                    continue

                for node in ast.walk(tree):
                    imported_pkg: str | None = None
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            top = alias.name.split(".")[0]
                            if top in module_packages:
                                imported_pkg = top
                                break
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        top = node.module.split(".")[0]
                        if top in module_packages:
                            imported_pkg = top

                    if imported_pkg:
                        diags.append(
                            Diagnostic(
                                level=DiagnosticLevel.ERROR,
                                code="SM009",
                                message=(
                                    f"Framework package '{fw_pkg}' directly imports "
                                    f"from module package '{imported_pkg}'"
                                ),
                                module_name=module_packages[imported_pkg],
                                file=str(py_file),
                                suggestion=(
                                    "Use a ModuleBase lifecycle hook "
                                    "(register_middleware, register_routes, etc.) "
                                    "instead of importing module code from the framework"
                                ),
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

    def _check_orphan_pages(
        self,
        mod: ModuleBase,
        src_dir: Path,
        rendered_pages: set[str],
    ) -> list[Diagnostic]:
        """Find .tsx pages that aren't referenced by any inertia.render() call."""
        pages_dir = src_dir / "pages"
        if not pages_dir.exists():
            return []

        tsx_pages = {f.stem for f in pages_dir.glob("*.tsx")}
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
        tsx_pages = {f.stem for f in pages_dir.glob("*.tsx")} if pages_dir.exists() else set()
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
        """Parse Python source to find inertia.render("Module/Page") calls."""
        rendered: set[str] = set()
        prefix = f"{mod.meta.name}/"

        for py_file in src_dir.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(), filename=str(py_file))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                # Match: inertia.render("Products/Browse", ...)
                # or: xxx.render("Products/Browse", ...)
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "render"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                ):
                    component = node.args[0].value
                    if isinstance(component, str) and component.startswith(prefix):
                        page_name = component[len(prefix) :]
                        rendered.add(page_name)

        return rendered

    def _find_source_dir(self, mod: ModuleBase) -> Path | None:
        """Locate the source directory for a module's package."""
        pkg_name = type(mod).__module__.rsplit(".", 1)[0]
        return self._find_package_dir(pkg_name)


class MigrationDiagnostics:
    """Validates database migration state."""

    def check_revision_mismatch(
        self,
        current_revision: str | None,
        head_revision: str | None,
    ) -> list[Diagnostic]:
        """SM010: Error if database is not at the migration head."""
        if current_revision == head_revision:
            return []
        return [
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="SM010",
                message=(f"Database at revision {current_revision!r}, expected {head_revision!r}"),
                module_name="migrations",
                suggestion="Run: make migrate",
            )
        ]

    def check_table_coverage(
        self,
        module_tables: set[str],
        migrated_tables: set[str],
    ) -> list[Diagnostic]:
        """SM011: Warning if module tables are missing from migration history."""
        missing = module_tables - migrated_tables
        return [
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code="SM011",
                message=f"Table '{table}' declared in models but not found in migration history",
                module_name="migrations",
                suggestion=f'Run: make migration msg="add {table}"',
            )
            for table in sorted(missing)
        ]


def run_diagnostics(
    modules: list[ModuleBase],
    *,
    migration_state: dict | None = None,
    module_tables: set[str] | None = None,
    migrated_tables: set[str] | None = None,
) -> list[Diagnostic]:
    """Convenience function to run all diagnostics.

    When ``migration_state`` is provided, also runs migration diagnostics.
    """
    diagnostics = ModuleDiagnostics().run(modules)

    if migration_state is not None:
        migration_diag = MigrationDiagnostics()
        diagnostics.extend(
            migration_diag.check_revision_mismatch(
                current_revision=migration_state.get("current_revision"),
                head_revision=migration_state.get("head_revision"),
            )
        )
        if module_tables is not None and migrated_tables is not None:
            diagnostics.extend(migration_diag.check_table_coverage(module_tables, migrated_tables))

    return diagnostics


def print_diagnostics(diagnostics: list[Diagnostic]) -> None:
    """Pretty-print diagnostics to stderr."""
    if not diagnostics:
        logger.info("\u2713 No module diagnostics issues found")
        return

    errors = [d for d in diagnostics if d.level == DiagnosticLevel.ERROR]
    warnings = [d for d in diagnostics if d.level == DiagnosticLevel.WARNING]
    infos = [d for d in diagnostics if d.level == DiagnosticLevel.INFO]

    for d in diagnostics:
        print(str(d), file=sys.stderr)
        print(file=sys.stderr)

    print(
        f"Results: {len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info",
        file=sys.stderr,
    )
