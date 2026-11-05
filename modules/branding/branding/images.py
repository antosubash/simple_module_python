"""Moved to :mod:`branding.assets.images`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("branding.images", remove_in="0.0.46", use="branding.assets.images")
sys.modules[__name__] = importlib.import_module("branding.assets.images")
