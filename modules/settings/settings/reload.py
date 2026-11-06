"""Moved to :mod:`settings.module_settings.reload`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("settings.reload", remove_in="0.0.46", use="settings.module_settings.reload")
sys.modules[__name__] = importlib.import_module("settings.module_settings.reload")
