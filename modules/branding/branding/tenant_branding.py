"""Moved to :mod:`branding.core.tenant_branding`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module(
    "branding.tenant_branding", remove_in="0.0.46", use="branding.core.tenant_branding"
)
sys.modules[__name__] = importlib.import_module("branding.core.tenant_branding")
