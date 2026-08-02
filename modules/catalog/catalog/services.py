"""Module-scoped state container.

Stored as ``app.state.catalog`` by
:meth:`CatalogModule.register_settings`.

Not frozen — ``on_startup`` may set fields that depend on the DB or
other framework services. Convention: set once during boot, treat as
read-only after.
"""

from __future__ import annotations

from dataclasses import dataclass

from catalog.settings import CatalogSettings


@dataclass
class CatalogServices:
    """Catalog module singletons."""

    settings: CatalogSettings
