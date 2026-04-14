"""Run module diagnostics from the command line.

Usage::

    python -m simple_module_core        # discover modules, run diagnostics
    make doctor                         # same thing, wrapped

Exits with status 1 if any ERROR-level diagnostics are reported.
"""

from __future__ import annotations

import sys

from simple_module_core.diagnostics import (
    DiagnosticLevel,
    print_diagnostics,
    run_diagnostics,
)
from simple_module_core.discovery import discover_modules, topological_sort


def main() -> int:
    modules = discover_modules()
    if not modules:
        print("No modules discovered. Is the project installed (`uv sync --all-packages`)?")
        return 0

    # Topological sort surfaces CircularDependencyError early.
    modules = topological_sort(modules)

    diagnostics = run_diagnostics(modules)
    print_diagnostics(diagnostics)

    errors = [d for d in diagnostics if d.level == DiagnosticLevel.ERROR]
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
