"""Moved to :mod:`tenants.core.constants`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("tenants.constants", remove_in="0.0.46", use="tenants.core.constants")
sys.modules[__name__] = importlib.import_module("tenants.core.constants")
