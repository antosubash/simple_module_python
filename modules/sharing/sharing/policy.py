"""Moved to :mod:`sharing.core.policy`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("sharing.policy", remove_in="0.0.46", use="sharing.core.policy")
sys.modules[__name__] = importlib.import_module("sharing.core.policy")
