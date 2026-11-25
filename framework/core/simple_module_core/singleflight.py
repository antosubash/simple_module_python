"""Deprecated alias for simple_module_core.runtime.singleflight."""

import sys
from importlib import import_module

from simple_module_core.runtime.deprecation import deprecated_module

deprecated_module(
    "simple_module_core.singleflight",
    remove_in="0.0.55",
    use="simple_module_core.runtime.singleflight",
)
sys.modules[__name__] = import_module("simple_module_core.runtime.singleflight")
