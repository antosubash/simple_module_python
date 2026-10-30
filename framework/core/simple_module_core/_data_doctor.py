"""Optional database diagnostics for Doctor without requiring a host app import."""

import asyncio
import importlib.util
import os
from collections.abc import Sequence

from simple_module_core.diagnostics import Diagnostic
from simple_module_core.module import ModuleBase


def data_compatibility_diagnostics(modules: Sequence[ModuleBase]) -> list[Diagnostic]:
    # Core-only installations have no database runtime to inspect.
    if importlib.util.find_spec("simple_module_db") is None:
        return []
    if all(
        type(mod).check_data_compatibility is ModuleBase.check_data_compatibility for mod in modules
    ):
        return []
    from simple_module_db.data_compatibility import database_compatibility_diagnostics

    url = os.environ.get("SM_DATABASE_URL", "sqlite+aiosqlite:///./app.db")
    return asyncio.run(database_compatibility_diagnostics(modules, url))
