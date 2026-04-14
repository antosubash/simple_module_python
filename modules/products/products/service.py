"""Product service implementation."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from products.contracts.schemas import ProductCreate, ProductOut, ProductUpdate
from products.models import Product


class ProductService:
    """CRUD operations for products."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all(
        self,
        *,
        page: int = 1,
        per_page: int = 10,
        search: str | None = None,
    ) -> tuple[list[ProductOut], int]:
        """Return paginated products and total count."""
        query = select(Product).where(Product.is_active.is_(True))
        count_query = select(func.count()).select_from(Product).where(Product.is_active.is_(True))

        if search:
            pattern = f"%{search}%"
            search_filter = Product.name.ilike(pattern) | Product.description.ilike(pattern)
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.order_by(Product.id).offset((page - 1) * per_page).limit(per_page)
        result = await self.db.execute(query)
        products = [ProductOut.model_validate(p) for p in result.scalars()]

        return products, total

    async def get_by_id(self, product_id: int) -> ProductOut | None:
        result = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
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
        result = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if product is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(product, field, value)
        await self.db.flush()
        await self.db.refresh(product)
        return ProductOut.model_validate(product)

    async def delete(self, product_id: int) -> bool:
        result = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if product is None:
            return False
        await self.db.delete(product)
        await self.db.flush()
        return True
