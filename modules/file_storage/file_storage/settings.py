"""Moved to :mod:`file_storage.core.settings`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("file_storage.settings", remove_in="0.0.46", use="file_storage.core.settings")
sys.modules[__name__] = importlib.import_module("file_storage.core.settings")
