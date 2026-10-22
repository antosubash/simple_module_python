"""Module-scoped state container.

Stored as ``app.state.sharing`` by
:meth:`SharingModule.register_settings`.

Not frozen — ``on_startup`` may set fields that depend on the DB or
other framework services. Convention: set once during boot, treat as
read-only after.
"""

from __future__ import annotations

from dataclasses import dataclass

from sharing.settings import SharingSettings


@dataclass
class SharingServices:
    """Sharing module singletons."""

    settings: SharingSettings
