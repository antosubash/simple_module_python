"""SM017: warn modules shipping .tsx pages but missing npm workspace files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase


def check_js_workspace_files(mod: ModuleBase, src_dir: Path) -> list[Diagnostic]:
    """Warn when a module ships .tsx pages but is missing npm workspace files."""
    pages_dir = src_dir / "pages"
    if not pages_dir.exists() or not any(pages_dir.rglob("*.tsx")):
        return []
    module_dir = src_dir.parent
    return [
        Diagnostic(
            level=DiagnosticLevel.WARNING,
            code="SM017",
            message=f"Module ships pages/*.tsx but has no {fn}",
            module_name=mod.meta.name,
            file=str(module_dir / fn),
            suggestion=(
                f"Create {module_dir / fn} — without it npm won't treat the "
                "module as a workspace member and Vite may fail to resolve "
                "@simple-module/ui subpath imports"
            ),
        )
        for fn in ("package.json", "tsconfig.json")
        if not (module_dir / fn).exists()
    ]
