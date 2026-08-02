"""Catalog service implementation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.contracts.schemas import (
    CatalogCreate,
    CatalogOut,
    CatalogUpdate,
)
from catalog.models import Catalog


class CatalogService:
    """CRUD operations for catalog."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all(self) -> list[CatalogOut]:
        result = await self.db.execute(
            select(Catalog)
            .where(Catalog.is_active.is_(True))
            .order_by(Catalog.id)
        )
        return [CatalogOut.model_validate(row) for row in result.scalars()]

    async def get_by_id(self, catalog_id: int) -> CatalogOut | None:
        entity = await self.db.get(Catalog, catalog_id)
        if entity is None:
            return None
        return CatalogOut.model_validate(entity)

    async def create(self, data: CatalogCreate) -> CatalogOut:
        entity = Catalog(**data.model_dump())
        self.db.add(entity)
        await self.db.flush()
        await self.db.refresh(entity)
        return CatalogOut.model_validate(entity)

    async def update(
        self, catalog_id: int, data: CatalogUpdate
    ) -> CatalogOut | None:
        entity = await self.db.get(Catalog, catalog_id)
        if entity is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(entity, field, value)
        await self.db.flush()
        await self.db.refresh(entity)
        return CatalogOut.model_validate(entity)

    async def delete(self, catalog_id: int) -> bool:
        entity = await self.db.get(Catalog, catalog_id)
        if entity is None:
            return False
        await self.db.delete(entity)
        return True
