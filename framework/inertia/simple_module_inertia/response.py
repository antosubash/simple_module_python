"""Deprecated response import path; use simple_module_inertia.protocol.response."""

import sys
import warnings
from importlib import import_module

warnings.warn(
    "simple_module_inertia.response is deprecated and will be removed in 0.0.52; "
    "use simple_module_inertia.protocol.response instead",
    DeprecationWarning,
    stacklevel=2,
)
sys.modules[__name__] = import_module("simple_module_inertia.protocol.response")
