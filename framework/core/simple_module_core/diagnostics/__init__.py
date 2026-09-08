"""Module diagnostics — validates structure and patterns at startup or via CLI.

This is the public surface re-exported from the submodules below.
Callers import from ``simple_module_core.diagnostics`` and should not
need to reach into ``._module`` or ``._migration`` directly.
"""

from __future__ import annotations

from simple_module_core.diagnostics._i18n import I18nDiagnostics
from simple_module_core.diagnostics._migration import MigrationDiagnostics
from simple_module_core.diagnostics._module import ModuleDiagnostics
from simple_module_core.diagnostics._pages import collect_tsx_pages
from simple_module_core.diagnostics._runner import print_diagnostics, run_diagnostics
from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

__all__ = [
    "Diagnostic",
    "DiagnosticLevel",
    "I18nDiagnostics",
    "MigrationDiagnostics",
    "ModuleDiagnostics",
    "collect_tsx_pages",
    "print_diagnostics",
    "run_diagnostics",
]
