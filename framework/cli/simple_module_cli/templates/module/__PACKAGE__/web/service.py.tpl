"""{{SINGULAR_CLASS}} service implementation.

Business failures raise domain exceptions derived from a per-module base in
exceptions.py or errors.py, never HTTPException. Map them in endpoints or via
ModuleBase.register_exception_handlers; keep HTTP status, payload, headers and
translation at that boundary so this service also works in CLI/tasks.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from {{PACKAGE_NAME}}.contracts.schemas import (
    {{SINGULAR_CLASS}}Create,
    {{SINGULAR_CLASS}}Out,
    {{SINGULAR_CLASS}}Update,
)
from {{PACKAGE_NAME}}.models import {{SINGULAR_CLASS}}


class {{SINGULAR_CLASS}}Service:
    """CRUD operations for {{PACKAGE_NAME}}."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all(self) -> list[{{SINGULAR_CLASS}}Out]:
        model = {{SINGULAR_CLASS}}
        result = await self.db.execute(select(model).order_by(col(model.id)))
        return [{{SINGULAR_CLASS}}Out.model_validate(row) for row in result.scalars()]

    async def get_by_id(self, item_id: int) -> {{SINGULAR_CLASS}}Out | None:
        entity = await self.db.get({{SINGULAR_CLASS}}, item_id)
        if entity is None:
            return None
        return {{SINGULAR_CLASS}}Out.model_validate(entity)

    async def create(self, data: {{SINGULAR_CLASS}}Create) -> {{SINGULAR_CLASS}}Out:
        entity = {{SINGULAR_CLASS}}(**data.model_dump())
        self.db.add(entity)
        await self.db.flush()
        await self.db.refresh(entity)
        return {{SINGULAR_CLASS}}Out.model_validate(entity)

    async def update(
        self,
        item_id: int,
        data: {{SINGULAR_CLASS}}Update,
    ) -> {{SINGULAR_CLASS}}Out | None:
        entity = await self.db.get({{SINGULAR_CLASS}}, item_id)
        if entity is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(entity, field, value)
        await self.db.flush()
        await self.db.refresh(entity)
        return {{SINGULAR_CLASS}}Out.model_validate(entity)

    async def delete(self, item_id: int) -> bool:
        entity = await self.db.get({{SINGULAR_CLASS}}, item_id)
        if entity is None:
            return False
        await self.db.delete(entity)
        return True
