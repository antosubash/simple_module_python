"""Moved to :mod:`file_storage.core.tenant_deletion`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module(
    "file_storage.tenant_deletion", remove_in="0.0.46", use="file_storage.core.tenant_deletion"
)
sys.modules[__name__] = importlib.import_module("file_storage.core.tenant_deletion")
