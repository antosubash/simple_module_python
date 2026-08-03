"""Branding service — reads current branding and applies admin changes.

There is no branding DB table: values live in the shared settings store. Writes
go through ``settings.reload.apply_changes_and_reload`` which validates against
``BrandingSettings``, persists (SYSTEM scope), hot-swaps ``app.state.branding``
and publishes ``SettingsReloaded``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from branding.constants import PACKAGE
from branding.contracts.schemas import BrandingOut
from branding.shared_props import file_url

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession


class BrandingService:
    """Read/update the application's branding."""

    def __init__(self, app: FastAPI, db: AsyncSession) -> None:
        self.app = app
        self.db = db

    def current(self) -> BrandingOut:
        settings = self.app.state.branding.settings
        return BrandingOut(
            app_name=settings.app_name,
            primary_color=settings.primary_color,
            design_pack=settings.design_pack,
            logo_url=file_url(settings.logo_file_id),
            favicon_url=file_url(settings.favicon_file_id),
        )

    async def apply(self, changes: dict[str, Any]) -> BrandingOut:
        """Persist and hot-swap the given field changes, then return current."""
        # Plugin→plugin imports (settings is a declared dependency); kept local
        # so import order during discovery stays tolerant.
        from settings.reload import apply_changes_and_reload
        from settings.service import SettingService
        from settings.store import SettingsStore

        store = SettingsStore(SettingService(self.db))
        bus = self.app.state.sm.event_bus
        await apply_changes_and_reload(self.app, bus, store, package=PACKAGE, changes=changes)
        return self.current()

    async def set_logo(self, file_id: str) -> BrandingOut:
        return await self.apply({"logo_file_id": file_id})

    async def set_favicon(self, file_id: str) -> BrandingOut:
        return await self.apply({"favicon_file_id": file_id})

    async def clear_logo(self) -> BrandingOut:
        return await self.apply({"logo_file_id": ""})

    async def clear_favicon(self) -> BrandingOut:
        return await self.apply({"favicon_file_id": ""})
