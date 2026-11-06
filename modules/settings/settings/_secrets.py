"""Moved to :mod:`settings.core._secrets`; this alias goes in 0.1.0 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("settings._secrets", remove_in="0.1.0", use="settings.core._secrets")
sys.modules[__name__] = importlib.import_module("settings.core._secrets")
