"""Moved to :mod:`file_storage.files.service`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("file_storage.service", remove_in="0.0.46", use="file_storage.files.service")
sys.modules[__name__] = importlib.import_module("file_storage.files.service")
