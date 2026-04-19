"""Module-scoped state container.

Stored as ``app.state.settings`` by
:meth:`SettingsModule.register_settings`.

Not frozen — ``on_startup`` may set fields that depend on the DB or
other framework services. Convention: set once during boot, treat as
read-only after.
"""

from __future__ import annotations

from dataclasses import dataclass

from settings.settings import SettingsSettings


@dataclass
class SettingsServices:
    """Settings module singletons."""

    settings: SettingsSettings
