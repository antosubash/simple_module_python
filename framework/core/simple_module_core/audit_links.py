"""Deprecated alias for simple_module_core.web.audit_links."""

import sys
from importlib import import_module

from simple_module_core.runtime.deprecation import deprecated_module

deprecated_module(
    "simple_module_core.audit_links", remove_in="0.0.55", use="simple_module_core.web.audit_links"
)
sys.modules[__name__] = import_module("simple_module_core.web.audit_links")
