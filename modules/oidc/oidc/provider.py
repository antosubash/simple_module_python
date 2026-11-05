"""Moved to :mod:`oidc.identity.provider`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("oidc.provider", remove_in="0.0.46", use="oidc.identity.provider")
sys.modules[__name__] = importlib.import_module("oidc.identity.provider")
