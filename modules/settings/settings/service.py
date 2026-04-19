"""Setting service implementation — scoped key/value CRUD + resolution."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from settings.constants import SYSTEM_SCOPE_ID, VALUE_TYPE_STRING
from settings.contracts.schemas import (
    SettingCreate,
    SettingOut,
    SettingScope,
    SettingUpdate,
    SettingUpsert,
)
from settings.models import Setting


class SettingService:
    """Async CRUD + scope resolution for key/value settings.

    Resolution precedence when calling ``resolve`` / ``get_resolved_value``:
    USER > TENANT > SYSTEM. The first match in that chain is returned.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Listing ─────────────────────────────────────────────────────

    async def list_all(self) -> list[SettingOut]:
        result = await self.db.execute(
            select(Setting).order_by(Setting.scope, Setting.scope_id, Setting.key)
        )
        return [SettingOut.model_validate(row) for row in result.scalars()]

    async def list_by_scope(
        self, scope: SettingScope, scope_id: str = SYSTEM_SCOPE_ID
    ) -> list[SettingOut]:
        stmt = (
            select(Setting)
            .where(Setting.scope == scope.value, Setting.scope_id == scope_id)
            .order_by(Setting.key)
        )
        result = await self.db.execute(stmt)
        return [SettingOut.model_validate(row) for row in result.scalars()]

    # ── Lookup ──────────────────────────────────────────────────────

    async def get_by_id(self, setting_id: int) -> SettingOut | None:
        entity = await self.db.get(Setting, setting_id)
        if entity is None:
            return None
        return SettingOut.model_validate(entity)

    async def get_scoped(self, scope: SettingScope, scope_id: str, key: str) -> SettingOut | None:
        entity = await self._find(scope, scope_id, key)
        return SettingOut.model_validate(entity) if entity is not None else None

    async def resolve(
        self,
        key: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> SettingOut | None:
        if user_id:
            entity = await self._find(SettingScope.USER, user_id, key)
            if entity is not None:
                return SettingOut.model_validate(entity)
        if tenant_id:
            entity = await self._find(SettingScope.TENANT, tenant_id, key)
            if entity is not None:
                return SettingOut.model_validate(entity)
        entity = await self._find(SettingScope.SYSTEM, SYSTEM_SCOPE_ID, key)
        return SettingOut.model_validate(entity) if entity is not None else None

    async def get_resolved_value(
        self,
        key: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        default: str | None = None,
    ) -> str | None:
        found = await self.resolve(key, user_id=user_id, tenant_id=tenant_id)
        return found.value if found is not None else default

    # ── Mutations ───────────────────────────────────────────────────

    async def create(self, data: SettingCreate) -> SettingOut:
        entity = Setting(**data.model_dump())
        self.db.add(entity)
        await self.db.flush()
        await self.db.refresh(entity)
        return SettingOut.model_validate(entity)

    async def update(self, setting_id: int, data: SettingUpdate) -> SettingOut | None:
        entity = await self.db.get(Setting, setting_id)
        if entity is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(entity, field, value)
        await self.db.flush()
        await self.db.refresh(entity)
        return SettingOut.model_validate(entity)

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
            self.db.add(entity)
        else:
            entity.value = data.value
            if data.value_type is not None:
                entity.value_type = data.value_type.value
            # Honor explicit description=None as "clear"; skip only when unset.
            if "description" in data.model_fields_set:
                entity.description = data.description
        await self.db.flush()
        await self.db.refresh(entity)
        return SettingOut.model_validate(entity)

    async def delete(self, setting_id: int) -> bool:
        entity = await self.db.get(Setting, setting_id)
        if entity is None:
            return False
        await self.db.delete(entity)
        await self.db.flush()
        return True

    async def delete_scoped(self, scope: SettingScope, scope_id: str, key: str) -> bool:
        entity = await self._find(scope, scope_id, key)
        if entity is None:
            return False
        await self.db.delete(entity)
        await self.db.flush()
        return True

    # ── Internals ───────────────────────────────────────────────────

    async def _find(self, scope: SettingScope, scope_id: str, key: str) -> Setting | None:
        stmt = select(Setting).where(
            Setting.scope == scope.value,
            Setting.scope_id == scope_id,
            Setting.key == key,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
