"""Moved to :mod:`file_storage.multipart.support`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module(
    "file_storage.upload_support", remove_in="0.0.46", use="file_storage.multipart.support"
)
sys.modules[__name__] = importlib.import_module("file_storage.multipart.support")
