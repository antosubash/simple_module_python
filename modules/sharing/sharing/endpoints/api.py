"""Moved to :mod:`sharing.web.endpoints.api`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("sharing.endpoints.api", remove_in="0.0.46", use="sharing.web.endpoints.api")
sys.modules[__name__] = importlib.import_module("sharing.web.endpoints.api")
