"""Module-scoped state container.

Stored as ``app.state.branding`` by
:meth:`BrandingModule.register_settings` (via ``register_module_settings``).
``settings`` is hot-swapped by ``settings.reload.apply_changes_and_reload`` when
an admin saves changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from branding.settings import BrandingSettings


@dataclass
class BrandingServices:
    """Branding module singletons."""

    settings: BrandingSettings
