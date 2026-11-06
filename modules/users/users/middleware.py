"""Moved to :mod:`auth.web.middleware`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("users.middleware", remove_in="0.0.46", use="auth.web.middleware")
sys.modules[__name__] = importlib.import_module("auth.web.middleware")
