"""Deprecated: import from :mod:`simple_module_core.module_settings` (#500).

Kept as a re-export until 0.1.0 at the earliest.
"""

from __future__ import annotations

import warnings

from simple_module_core.module_settings import register_module_settings

__all__ = ["register_module_settings"]

warnings.warn(
    "settings.registration is deprecated; import register_module_settings from "
    "simple_module_core.module_settings",
    DeprecationWarning,
    # Attribute the warning to the importer, not importlib's frozen frames.
    skip_file_prefixes=("<frozen importlib",),
)
