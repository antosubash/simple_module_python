"""Deprecated alias for simple_module_db.engine.engine_options."""

import sys
from importlib import import_module

from simple_module_core.runtime.deprecation import deprecated_module

deprecated_module(
    "simple_module_db.engine_options",
    remove_in="0.0.52",
    use="simple_module_db.engine.engine_options",
)
sys.modules[__name__] = import_module("simple_module_db.engine.engine_options")
