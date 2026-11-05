"""Moved to :mod:`feature_flags.core.constants`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("feature_flags.constants", remove_in="0.0.46", use="feature_flags.core.constants")
sys.modules[__name__] = importlib.import_module("feature_flags.core.constants")
