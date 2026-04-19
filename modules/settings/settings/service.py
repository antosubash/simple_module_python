"""Setting service implementation — key/value CRUD + upsert."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from settings.contracts.schemas import (
    SettingCreate,
    SettingOut,
    SettingUpdate,
    SettingUpsert,
)
from settings.models import Setting


class SettingService:
    """Async CRUD + upsert for key/value settings."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(self) -> list[SettingOut]:
        result = await self.db.execute(select(Setting).order_by(Setting.key))
        return [SettingOut.model_validate(row) for row in result.scalars()]

    async def get_by_id(self, setting_id: int) -> SettingOut | None:
        entity = await self.db.get(Setting, setting_id)
        if entity is None:
            return None
        return SettingOut.model_validate(entity)

    async def get_by_key(self, key: str) -> SettingOut | None:
        entity = await self._find_by_key(key)
        if entity is None:
            return None
        return SettingOut.model_validate(entity)

    async def get_value(self, key: str, default: str | None = None) -> str | None:
        entity = await self._find_by_key(key)
        return entity.value if entity is not None else default

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

    async def upsert_by_key(self, key: str, data: SettingUpsert) -> SettingOut:
        entity = await self._find_by_key(key)
        if entity is None:
            entity = Setting(key=key, value=data.value, description=data.description)
            self.db.add(entity)
        else:
            entity.value = data.value
            if data.description is not None:
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

    async def delete_by_key(self, key: str) -> bool:
        entity = await self._find_by_key(key)
        if entity is None:
            return False
        await self.db.delete(entity)
        await self.db.flush()
        return True

    async def _find_by_key(self, key: str) -> Setting | None:
        result = await self.db.execute(select(Setting).where(Setting.key == key))
        return result.scalar_one_or_none()
