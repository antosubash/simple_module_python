"""SM030 — a module ``depends_on`` a module that is not loaded (GH #501).

A development boot logs it and carries on; ``make doctor`` reports it as an
error; any other environment refuses to boot (``topological_sort(strict=True)``
raises ``MissingDependencyError``). The usual cause is an auth provider other
than ``users``: selecting it drops ``Users``, and every module that still
depends on it (``permissions``, ``api_tokens``) has to be left out too.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

CODE = "SM030"


def check_missing_dependencies(
    modules: list[ModuleBase], level: DiagnosticLevel = DiagnosticLevel.WARNING
) -> list[Diagnostic]:
    names = {m.meta.name for m in modules}
    return [
        Diagnostic(
            level=level,
            code=CODE,
            message=(
                f"Module '{mod.meta.name}' depends on '{dep}', which is not loaded; "
                "a non-development boot refuses to start"
            ),
            module_name=mod.meta.name,
            suggestion=(
                f"Install and enable '{dep}', or leave '{mod.meta.name}' out (SM_MODULES_ENABLED)"
            ),
        )
        for mod in modules
        for dep in mod.meta.depends_on
        if dep not in names
    ]
