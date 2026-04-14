"""FastAPI dependencies for the Products module."""

from __future__ import annotations

from fastapi import Depends
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from sm_products.service import ProductService


async def get_product_service(
    db: AsyncSession = Depends(get_db),
) -> ProductService:
    return ProductService(db)
