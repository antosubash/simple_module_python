"""Moved to :mod:`branding.core.settings`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("branding.settings", remove_in="0.0.46", use="branding.core.settings")
sys.modules[__name__] = importlib.import_module("branding.core.settings")
