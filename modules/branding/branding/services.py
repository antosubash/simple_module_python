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

    @property
    def favicon_url(self) -> str | None:
        """The favicon URL, or ``None`` when no custom favicon is set.

        Exposed here so the root template can emit ``<link rel="icon">`` before
        React hydrates, without framework code learning branding's route shape:
        ``branding_head`` reads this attribute duck-typed, exactly as it already
        reads ``settings.app_name``. Keeps the SM009 framework→plugin boundary
        intact — branding owns the URL, the framework only forwards it.
        """
        from branding.constants import FAVICON_URL
        from branding.shared_props import asset_url

        return asset_url(FAVICON_URL, self.settings.favicon_file_id)
