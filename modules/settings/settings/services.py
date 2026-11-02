"""Module-scoped state container.

Stored as ``app.state.settings`` by
:meth:`SettingsModule.register_settings`.

Not frozen — ``on_startup`` may set fields that depend on the DB or
other framework services. Convention: set once during boot, treat as
read-only after.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from simple_module_core.module_settings import ModuleSettingsRegistry

from settings.contracts.registry import SettingsRegistry
from settings.settings import SettingsSettings


@dataclass
class SettingsServices:
    """Settings module singletons.

    ``registry`` is shared across the whole app — consumer modules register
    their setting keys here (typically from their own ``on_startup`` hook)
    so admins can discover every knob and the accessor can fall back to
    declared defaults.

    ``module_registry`` is the framework's registry of per-module
    ``BaseSettings`` classes (``simple_module_core.module_settings``), the
    same object the hosting lifespan hydrates from the DB before
    ``on_startup`` runs.
    """

    settings: SettingsSettings
    registry: SettingsRegistry = field(default_factory=SettingsRegistry)
    module_registry: ModuleSettingsRegistry = field(default_factory=ModuleSettingsRegistry)
