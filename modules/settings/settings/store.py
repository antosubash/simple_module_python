"""Moved to :mod:`settings.module_settings.store`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("settings.store", remove_in="0.0.46", use="settings.module_settings.store")
sys.modules[__name__] = importlib.import_module("settings.module_settings.store")
