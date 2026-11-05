"""Moved to :mod:`oidc.identity.jwks`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module("oidc.jwks", remove_in="0.0.46", use="oidc.identity.jwks")
sys.modules[__name__] = importlib.import_module("oidc.identity.jwks")
