"""SM028: flag a ``tasks.py`` that imports a heavy package at module level.

Celery imports every installed module's ``tasks.py`` in each process that
loads the module (the web app, every worker, beat). A top-level
``import torch`` there makes all of them pay for it, and defeats the per-worker
subset (``SM_BG_TASKS_WORKER_QUEUES`` / ``include_modules``), which exists so a
light worker never imports the heavy one. Import the package inside the task
body instead. Uses ``ast`` and never imports the module being checked.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

HEAVY_PACKAGES = frozenset(
    {"torch", "tensorflow", "ultralytics", "osgeo", "rasterio", "cv2", "sklearn"}
)


def _heavy_roots(node: ast.stmt) -> list[str]:
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        names = [node.module]
    else:
        return []
    return [n.split(".", 1)[0] for n in names if n.split(".", 1)[0] in HEAVY_PACKAGES]


def _top_level_statements(body: list[ast.stmt]) -> list[ast.stmt]:
    """Statements that run at import time, descending into ``if``/``try``/``with``.

    Function and class bodies are skipped: an import there is deferred, which is
    the fix. ``if TYPE_CHECKING:`` blocks are skipped too — never executed.
    """
    out: list[ast.stmt] = []
    for node in body:
        out.append(node)
        if isinstance(node, ast.If):
            test = ast.unparse(node.test)
            if test in ("TYPE_CHECKING", "typing.TYPE_CHECKING"):
                out.extend(_top_level_statements(node.orelse))
                continue
            out.extend(_top_level_statements(node.body + node.orelse))
        elif isinstance(node, ast.Try):
            out.extend(
                _top_level_statements(
                    node.body + [s for h in node.handlers for s in h.body] + node.orelse
                )
            )
        elif isinstance(node, ast.With):
            out.extend(_top_level_statements(node.body))
    return out


def check_heavy_task_imports(mod: ModuleBase, src_dir: Path) -> list[Diagnostic]:
    """Warn when ``tasks.py`` imports a heavy package outside a function."""
    tasks_py = src_dir / "tasks.py"
    if not tasks_py.is_file():
        return []
    try:
        tree = ast.parse(tasks_py.read_text(), filename=str(tasks_py))
    except (OSError, SyntaxError):
        return []

    diags: list[Diagnostic] = []
    for node in _top_level_statements(tree.body):
        for root in _heavy_roots(node):
            diags.append(
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="SM028",
                    message=(
                        f"tasks.py imports heavy package '{root}' at module level — every "
                        "process that loads this module's tasks pays for it"
                    ),
                    module_name=mod.meta.name,
                    file=f"{tasks_py}:{node.lineno}",
                    suggestion=(
                        f"Move `import {root}` inside the task function, so only a worker "
                        "that actually runs the task loads it (and a queue-restricted "
                        "worker never does)."
                    ),
                )
            )
    return diags
