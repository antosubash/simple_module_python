"""SM017: report unusable optional frontend dependency manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.modules.module import ModuleBase


def check_js_workspace_files(mod: ModuleBase, src_dir: Path) -> list[Diagnostic]:
    """Frontend configs are optional; validate dependency declarations when present."""
    candidates = [src_dir / "package.json"]
    if "site-packages" not in src_dir.parts:
        candidates.append(src_dir.parent / "package.json")
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object")
            for block in ("dependencies", "peerDependencies", "devDependencies"):
                deps = data.get(block, {})
                if not isinstance(deps, dict) or not all(isinstance(v, str) for v in deps.values()):
                    raise ValueError(f"{block} must map package names to version strings")
        except (OSError, ValueError) as exc:
            return [
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="SM017",
                    message=f"Invalid frontend dependency manifest: {exc}",
                    module_name=mod.meta.name,
                    file=str(path),
                    suggestion=(
                        "Fix package.json, or remove it when no extra JS dependencies are needed."
                    ),
                )
            ]
        return []
    return []
