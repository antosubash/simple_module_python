"""Branding service — reads current branding and applies admin changes.

There is no branding DB table: values live in the shared settings store. Writes
go through ``settings.reload.apply_changes_and_reload`` which validates against
``BrandingSettings``, persists (SYSTEM scope), hot-swaps ``app.state.branding``
and publishes ``SettingsReloaded``.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from branding.constants import FAVICON_URL, LOGO_DARK_URL, LOGO_URL, PACKAGE
from branding.contracts.schemas import BrandingOut
from branding.shared_props import asset_url

if TYPE_CHECKING:
    from fastapi import FastAPI
    from file_storage.service import FileStorageService
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class BrandingService:
    """Read/update the application's branding."""

    def __init__(
        self,
        app: FastAPI,
        db: AsyncSession,
        storage: FileStorageService | None = None,
    ) -> None:
        self.app = app
        self.db = db
        # Optional so the published constructor stays backwards compatible.
        # Without it a replaced image simply isn't reaped — the rebrand itself
        # is unaffected. The module's own dependency always supplies one.
        self.storage = storage

    def current(self) -> BrandingOut:
        settings = self.app.state.branding.settings
        return BrandingOut(
            app_name=settings.app_name,
            primary_color=settings.primary_color,
            design_pack=settings.design_pack,
            logo_url=asset_url(LOGO_URL, settings.logo_file_id),
            logo_dark_url=asset_url(LOGO_DARK_URL, settings.logo_dark_file_id),
            favicon_url=asset_url(FAVICON_URL, settings.favicon_file_id),
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

    async def _swap_asset(self, field: str, file_id: str) -> BrandingOut:
        """Point *field* at *file_id* ("" to clear) and reap what it replaced.

        Every upload mints a new ``file_storage`` id, so the file we stop
        referencing here would otherwise sit in the store forever with nothing
        left to reference or reap it.
        """
        previous = getattr(self.app.state.branding.settings, field, "")
        out = await self.apply({field: file_id})
        if previous and previous != file_id:
            await self._reap(previous)
        return out

    async def _reap(self, file_id: str) -> None:
        """Delete a no-longer-referenced branding image, best effort.

        The setting change has already been persisted and is what the admin
        asked for, so a storage fault (or a hand-edited, non-UUID setting) must
        be logged rather than turned into a 500 on a successful rebrand.
        """
        if self.storage is None:
            return
        try:
            await self.storage.delete(uuid.UUID(file_id))
        except Exception:
            # Deliberately broad: any failure here is a cleanup problem, never
            # a reason to reject a rebrand the admin already succeeded at.
            logger.warning("Could not delete replaced branding image %s.", file_id, exc_info=True)

    async def set_logo(self, file_id: str) -> BrandingOut:
        return await self._swap_asset("logo_file_id", file_id)

    async def set_logo_dark(self, file_id: str) -> BrandingOut:
        return await self._swap_asset("logo_dark_file_id", file_id)

    async def clear_logo_dark(self) -> BrandingOut:
        return await self._swap_asset("logo_dark_file_id", "")

    async def set_favicon(self, file_id: str) -> BrandingOut:
        return await self._swap_asset("favicon_file_id", file_id)

    async def clear_logo(self) -> BrandingOut:
        return await self._swap_asset("logo_file_id", "")

    async def clear_favicon(self) -> BrandingOut:
        return await self._swap_asset("favicon_file_id", "")
