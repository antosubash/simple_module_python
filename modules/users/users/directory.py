"""Moved to :mod:`users.core.directory`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("users.directory", remove_in="0.0.46", use="users.core.directory")
sys.modules[__name__] = importlib.import_module("users.core.directory")
