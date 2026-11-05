"""Moved to :mod:`permissions.core.group_labels`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module(
    "permissions.group_labels", remove_in="0.0.46", use="permissions.core.group_labels"
)
sys.modules[__name__] = importlib.import_module("permissions.core.group_labels")
