"""Moved to :mod:`settings.core.constants`; this alias goes in 0.1.0 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("settings.constants", remove_in="0.1.0", use="settings.core.constants")
sys.modules[__name__] = importlib.import_module("settings.core.constants")
