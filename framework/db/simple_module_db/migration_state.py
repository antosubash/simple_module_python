"""Deprecated alias for simple_module_db.schema.migration_state."""

import sys
from importlib import import_module

from simple_module_core.runtime.deprecation import deprecated_module

deprecated_module(
    "simple_module_db.migration_state",
    remove_in="0.0.55",
    use="simple_module_db.schema.migration_state",
)
sys.modules[__name__] = import_module("simple_module_db.schema.migration_state")
