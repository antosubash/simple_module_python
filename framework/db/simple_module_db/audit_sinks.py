"""Deprecated alias for simple_module_db.auditing.audit_sinks."""

import sys
from importlib import import_module

from simple_module_core.runtime.deprecation import deprecated_module

deprecated_module(
    "simple_module_db.audit_sinks",
    remove_in="0.0.55",
    use="simple_module_db.auditing.audit_sinks",
)
sys.modules[__name__] = import_module("simple_module_db.auditing.audit_sinks")
