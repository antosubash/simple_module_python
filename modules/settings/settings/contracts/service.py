"""Setting service protocol — the public contract other modules depend on."""

from __future__ import annotations

from typing import Protocol

from settings.contracts.schemas import (
    SettingCreate,
    SettingOut,
    SettingUpdate,
)


class ISettingService(Protocol):
    """Interface for setting operations."""

    async def get_all(self) -> list[SettingOut]: ...
    async def get_by_id(self, setting_id: int) -> SettingOut | None: ...
    async def create(self, data: SettingCreate) -> SettingOut: ...
    async def update(self, setting_id: int, data: SettingUpdate) -> SettingOut | None: ...
    async def delete(self, setting_id: int) -> bool: ...
