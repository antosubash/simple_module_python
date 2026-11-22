"""Deprecated alias for simple_module_hosting.observability.sentry."""

import sys
from importlib import import_module

from simple_module_core.runtime.deprecation import deprecated_module

deprecated_module(
    "simple_module_hosting.sentry",
    remove_in="0.0.52",
    use="simple_module_hosting.observability.sentry",
)
sys.modules[__name__] = import_module("simple_module_hosting.observability.sentry")
