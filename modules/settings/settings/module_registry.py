"""Deprecated: import from :mod:`simple_module_core.module_settings` (#500).

Kept as a re-export until 0.1.0 at the earliest.
"""

from __future__ import annotations

import warnings

from simple_module_core.module_settings import ModuleSettingsRegistry

__all__ = ["ModuleSettingsRegistry"]

warnings.warn(
    "settings.module_registry is deprecated; import ModuleSettingsRegistry from "
    "simple_module_core.module_settings",
    DeprecationWarning,
    stacklevel=2,
)
