"""Moved to :mod:`api_tokens.credentials.resolver`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("api_tokens.resolver", remove_in="0.0.46", use="api_tokens.credentials.resolver")
sys.modules[__name__] = importlib.import_module("api_tokens.credentials.resolver")
