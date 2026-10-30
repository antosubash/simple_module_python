"""Optional database diagnostics for Doctor without requiring a host app import."""

import asyncio
import importlib.util
from collections.abc import Sequence

from simple_module_core.data_compatibility import checking_modules
from simple_module_core.diagnostics import Diagnostic
from simple_module_core.module import ModuleBase


def data_compatibility_diagnostics(
    modules: Sequence[ModuleBase], database_url: str
) -> list[Diagnostic]:
    # Core-only installations have no database runtime to inspect.
    if importlib.util.find_spec("simple_module_db") is None:
        return []
    if not checking_modules(modules):
        return []
    from simple_module_db.data_compatibility import database_compatibility_diagnostics

    return asyncio.run(database_compatibility_diagnostics(modules, database_url))
