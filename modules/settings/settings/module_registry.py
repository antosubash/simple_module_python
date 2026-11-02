"""Deprecated: import from :mod:`simple_module_core.module_settings` (#500).

Kept as a re-export until 0.1.0; ``simple_module_core.deprecation`` enforces the date.
"""

from __future__ import annotations

from simple_module_core.deprecation import deprecated_module
from simple_module_core.module_settings import ModuleSettingsRegistry

__all__ = ["ModuleSettingsRegistry"]

deprecated_module(
    "settings.module_registry",
    remove_in="0.1.0",
    use="simple_module_core.module_settings.ModuleSettingsRegistry",
)
