"""Setting service implementation — scoped key/value CRUD + resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from settings._announce import announce
from settings._listing import SettingListing
from settings._managed_keys import TenantIsLive, ensure_deletable
from settings._row_masking import drop_placeholder_write, is_placeholder_write, out
from settings._unique_write import DuplicateSettingError, insert_if_free
from settings.constants import (
    SYSTEM_SCOPE_ID,
    VALUE_TYPE_STRING,
)
from settings.contracts.schemas import (
    SettingCreate,
    SettingOut,
    SettingScope,
    SettingUpdate,
    SettingUpsert,
)
from settings.models import Setting

if TYPE_CHECKING:
    from simple_module_core.invalidation import InvalidationBus

    from settings.contracts.registry import SettingsRegistry


class SettingService(SettingListing):
    """Async CRUD + scope resolution for key/value settings.

    Resolution precedence when calling ``resolve`` / ``get_resolved_value``:
    USER > TENANT > SYSTEM. The first match in that chain is returned.
    """

    def __init__(
        self,
        db: AsyncSession,
        invalidation: InvalidationBus | None = None,
        registry: SettingsRegistry | None = None,
        tenant_is_live: TenantIsLive | None = None,
    ) -> None:
        self.db = db
        # With a registry, ``delete``/``delete_scoped`` refuse a ``clear_via``
        # key (see ``_managed_keys``); ``tenant_is_live`` lets a deleted
        # tenant's leftover row through.
        self.registry = registry
        self.tenant_is_live = tenant_is_live
        # When given, SYSTEM/TENANT writes announce themselves after commit so
        # per-tenant caches elsewhere drop the (tenant, key) they hold.
        self.invalidation = invalidation

    def _changed(self, entity: Setting) -> None:
        announce(self.db, self.invalidation, entity.scope, entity.scope_id, entity.key)

    # ── Lookup ──────────────────────────────────────────────────────

    async def get_by_id(self, setting_id: int) -> SettingOut | None:
        entity = await self.db.get(Setting, setting_id)
        if entity is None:
            return None
        return out(entity)

    async def get_scoped(self, scope: SettingScope, scope_id: str, key: str) -> SettingOut | None:
        entity = await self._find(scope, scope_id, key)
        return out(entity) if entity is not None else None

    async def _resolve_entity(
        self,
        key: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> Setting | None:
        """First match walking USER > TENANT > SYSTEM, unserialized."""
        if user_id:
            entity = await self._find(SettingScope.USER, user_id, key)
            if entity is not None:
                return entity
        if tenant_id:
            entity = await self._find(SettingScope.TENANT, tenant_id, key)
            if entity is not None:
                return entity
        return await self._find(SettingScope.SYSTEM, SYSTEM_SCOPE_ID, key)

    async def resolve(
        self,
        key: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> SettingOut | None:
        """The resolved row as the API returns it — masked if it is a secret."""
        entity = await self._resolve_entity(key, user_id=user_id, tenant_id=tenant_id)
        return out(entity) if entity is not None else None

    async def get_resolved_value(
        self,
        key: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        default: str | None = None,
    ) -> str | None:
        """The resolved *value*, unmasked — this is what consumers act on.

        ``SettingsAccessor`` is the read path other modules use to get a value
        they are about to use, not one they are about to render. Masking here
        would hand a module the placeholder instead of its own API key. The
        masked view of the same row is :meth:`resolve`, which is what the API
        returns.
        """
        entity = await self._resolve_entity(key, user_id=user_id, tenant_id=tenant_id)
        return entity.value if entity is not None else default

    # ── Mutations ───────────────────────────────────────────────────

    async def create(self, data: SettingCreate) -> SettingOut:
        entity = Setting(**data.model_dump())
        if not await insert_if_free(self.db, entity):
            raise DuplicateSettingError(f"{data.scope.value}/{data.scope_id}/{data.key}")
        await self.db.refresh(entity)
        self._changed(entity)
        return out(entity)

    async def update(self, setting_id: int, data: SettingUpdate) -> SettingOut | None:
        entity = await self.db.get(Setting, setting_id)
        if entity is None:
            return None
        changes = data.model_dump(exclude_unset=True)
        drop_placeholder_write(entity, changes)
        for field, value in changes.items():
            setattr(entity, field, value)
        await self.db.flush()
        await self.db.refresh(entity)
        self._changed(entity)
        return out(entity)

    async def upsert_scoped(
        self,
        scope: SettingScope,
        scope_id: str,
        key: str,
        data: SettingUpsert,
    ) -> SettingOut:
        entity = await self._find(scope, scope_id, key)
        if entity is None:
            entity = Setting(
                scope=scope.value,
                scope_id=scope_id,
                key=key,
                value=data.value,
                value_type=(
                    data.value_type.value if data.value_type is not None else VALUE_TYPE_STRING
                ),
                description=data.description,
            )
            # Two first-time writers can both get here; the loser's insert is
            # refused by the unique key, and it becomes an update of the winner's row.
            if await insert_if_free(self.db, entity):
                await self.db.refresh(entity)
                self._changed(entity)
                return out(entity)
            entity = await self._find(scope, scope_id, key)
            if entity is None:  # deleted again between the two statements
                raise DuplicateSettingError(f"{scope.value}/{scope_id}/{key}")
        if not is_placeholder_write(entity, data.value):
            entity.value = data.value
        if data.value_type is not None:
            entity.value_type = data.value_type.value
        # Honor explicit description=None as "clear"; skip only when unset.
        if "description" in data.model_fields_set:
            entity.description = data.description
        await self.db.flush()
        await self.db.refresh(entity)
        self._changed(entity)
        return out(entity)

    async def delete(self, setting_id: int, *, as_owner: bool = False) -> bool:
        entity = await self.db.get(Setting, setting_id)
        if entity is None:
            return False
        await self._remove(entity, as_owner)
        return True

    async def delete_scoped(
        self, scope: SettingScope, scope_id: str, key: str, *, as_owner: bool = False
    ) -> bool:
        """Delete one row; ``as_owner`` is for the module that reaps a ``clear_via`` key's file."""
        entity = await self._find(scope, scope_id, key)
        if entity is None:
            return False
        await self._remove(entity, as_owner)
        return True

    async def _remove(self, entity: Setting, as_owner: bool) -> None:
        if not as_owner:
            await ensure_deletable(
                self.registry, self.tenant_is_live, entity.scope, entity.scope_id, entity.key
            )
        self._changed(entity)
        await self.db.delete(entity)
        await self.db.flush()

    # ── Internals ───────────────────────────────────────────────────

    async def _find(self, scope: SettingScope, scope_id: str, key: str) -> Setting | None:
        stmt = select(Setting).where(
            Setting.scope == scope.value,
            Setting.scope_id == scope_id,
            Setting.key == key,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
