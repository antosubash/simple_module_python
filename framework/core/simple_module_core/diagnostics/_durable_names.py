"""SM034: flag a ``subscribe_durable(...)`` call without an explicit ``name=``.

A durable handler's outbox rows are keyed by its name, which defaults to the
handler's import path. Moving or renaming the handler module silently strands
every undelivered row (it retries as an unknown handler, then goes ``dead``).
Uses ``ast`` and never imports the module being checked.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

_SKIP_DIRS = frozenset({"tests", "node_modules", "__pycache__"})


def _is_unnamed_subscribe(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if called != "subscribe_durable":
        return False
    # A ``**kwargs`` spread may carry ``name``; give it the benefit of the doubt.
    return not any(kw.arg is None or kw.arg == "name" for kw in node.keywords)


def _source_files(src_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in src_dir.rglob("*.py")
        if not _SKIP_DIRS.intersection(p.relative_to(src_dir).parts)
    )


def check_durable_names(mod: ModuleBase, src_dir: Path) -> list[Diagnostic]:
    """Warn on each ``subscribe_durable`` call in the package that omits ``name=``."""
    diags: list[Diagnostic] = []
    for path in _source_files(src_dir):
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not _is_unnamed_subscribe(node):
                continue
            diags.append(
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="SM034",
                    message=(
                        "subscribe_durable(...) has no name= — the default name is the "
                        "handler's import path, so moving or renaming the handler strands "
                        "its undelivered outbox rows"
                    ),
                    module_name=mod.meta.name,
                    file=f"{path}:{node.lineno}",
                    suggestion=(
                        "Pass name= with a constant from constants.py whose value is the "
                        "current default name (module.path.function), so delivery state "
                        "survives refactors."
                    ),
                )
            )
    return diags
