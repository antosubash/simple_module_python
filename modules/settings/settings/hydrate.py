"""Deprecated: hydration moved to the framework (#500).

``simple_module_core.settings_hydrate`` holds the hydrator and field helpers;
the sync worker twin is ``simple_module_db.stored_settings.hydrate_settings_sync``.
Kept as a re-export until 0.1.0; ``simple_module_core.deprecation`` enforces the date.
"""

from __future__ import annotations

from simple_module_core.deprecation import deprecated_module
from simple_module_core.settings_hydrate import (
    RELATED_FIELDS_CTX,
    build_settings,
    env_supplied_fields,
    hydrate_settings,
    input_type_for_field,
    value_type_for_field,
)
from simple_module_db.stored_settings import hydrate_settings_sync

__all__ = [
    "RELATED_FIELDS_CTX",
    "build_settings",
    "env_supplied_fields",
    "hydrate_settings",
    "hydrate_settings_sync",
    "input_type_for_field",
    "value_type_for_field",
]

deprecated_module(
    "settings.hydrate",
    remove_in="0.1.0",
    use="simple_module_core.settings_hydrate (hydrate_settings_sync: "
    "simple_module_db.stored_settings)",
)
