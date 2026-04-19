"""Setting service protocol — the public contract other modules depend on."""

from __future__ import annotations

from typing import Protocol

from settings.contracts.schemas import (
    SettingCreate,
    SettingOut,
    SettingScope,
    SettingUpdate,
    SettingUpsert,
)


class ISettingService(Protocol):
    """Interface for scoped key/value settings.

    Resolution precedence (high → low): USER > TENANT > SYSTEM.
    """

    async def list_all(self) -> list[SettingOut]: ...
    async def list_by_scope(self, scope: SettingScope, scope_id: str = "") -> list[SettingOut]: ...

    async def get_by_id(self, setting_id: int) -> SettingOut | None: ...
    async def get_scoped(
        self, scope: SettingScope, scope_id: str, key: str
    ) -> SettingOut | None: ...
    async def resolve(
        self,
        key: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> SettingOut | None: ...
    async def get_resolved_value(
        self,
        key: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        default: str | None = None,
    ) -> str | None: ...

    async def create(self, data: SettingCreate) -> SettingOut: ...
    async def update(self, setting_id: int, data: SettingUpdate) -> SettingOut | None: ...
    async def upsert_scoped(
        self, scope: SettingScope, scope_id: str, key: str, data: SettingUpsert
    ) -> SettingOut: ...

    async def delete(self, setting_id: int) -> bool: ...
    async def delete_scoped(self, scope: SettingScope, scope_id: str, key: str) -> bool: ...
