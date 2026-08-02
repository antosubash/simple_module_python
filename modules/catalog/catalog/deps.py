"""FastAPI dependencies for the Catalog module."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.service import CatalogService


async def get_catalog_service(
    db: AsyncSession = Depends(get_db),
) -> CatalogService:
    return CatalogService(db)


CatalogServiceDep = Annotated[CatalogService, Depends(get_catalog_service)]
