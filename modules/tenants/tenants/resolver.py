"""Moved to :mod:`tenants.resolution.resolver`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("tenants.resolver", remove_in="0.0.46", use="tenants.resolution.resolver")
sys.modules[__name__] = importlib.import_module("tenants.resolution.resolver")
