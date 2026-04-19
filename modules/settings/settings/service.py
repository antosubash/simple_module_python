"""Setting service implementation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from settings.contracts.schemas import (
    SettingCreate,
    SettingOut,
    SettingUpdate,
)
from settings.models import Setting


class SettingService:
    """CRUD operations for settings."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all(self) -> list[SettingOut]:
        result = await self.db.execute(
            select(Setting).where(Setting.is_active.is_(True)).order_by(Setting.id)
        )
        return [SettingOut.model_validate(row) for row in result.scalars()]

    async def get_by_id(self, setting_id: int) -> SettingOut | None:
        entity = await self.db.get(Setting, setting_id)
        if entity is None:
            return None
        return SettingOut.model_validate(entity)

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

    async def delete(self, setting_id: int) -> bool:
        entity = await self.db.get(Setting, setting_id)
        if entity is None:
            return False
        await self.db.delete(entity)
        return True
