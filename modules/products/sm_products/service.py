"""Product service implementation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sm_products.contracts.schemas import ProductCreate, ProductOut, ProductUpdate
from sm_products.models import Product


class ProductService:
    """CRUD operations for products."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all(self) -> list[ProductOut]:
        result = await self.db.execute(
            select(Product).where(Product.is_active.is_(True)).order_by(Product.id)
        )
        return [ProductOut.model_validate(p) for p in result.scalars()]

    async def get_by_id(self, product_id: int) -> ProductOut | None:
        product = await self.db.get(Product, product_id)
        if product is None:
            return None
        return ProductOut.model_validate(product)

    async def create(self, data: ProductCreate) -> ProductOut:
        product = Product(**data.model_dump())
        self.db.add(product)
        await self.db.flush()
        await self.db.refresh(product)
        return ProductOut.model_validate(product)

    async def update(self, product_id: int, data: ProductUpdate) -> ProductOut | None:
        product = await self.db.get(Product, product_id)
        if product is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(product, field, value)
        await self.db.flush()
        await self.db.refresh(product)
        return ProductOut.model_validate(product)

    async def delete(self, product_id: int) -> bool:
        product = await self.db.get(Product, product_id)
        if product is None:
            return False
        await self.db.delete(product)
        return True
