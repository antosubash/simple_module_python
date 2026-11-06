"""Moved to :mod:`users.core.bootstrap`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("users.bootstrap", remove_in="0.0.46", use="users.core.bootstrap")
sys.modules[__name__] = importlib.import_module("users.core.bootstrap")
