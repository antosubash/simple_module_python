"""Read-only query service for catalog products.

Uses the column-query pattern established across this codebase's list
endpoints: select exactly the DTO's columns and count the same conditions
directly, rather than hydrating full ORM objects per page and wrapping the
count in a subquery.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SORT_CREATED,
    SORT_NAME,
    SORT_PRICE,
)
from catalog.contracts.schemas import CategoryRead, ProductList, ProductRead
from catalog.models import Category, Product

_PRODUCT_COLUMNS = (
    Product.id,
    Product.sku,
    Product.name,
    Product.description,
    Product.status,
    Product.price_cents,
    Product.category_id,
    Product.created_at,
)


def _sort_clause(sort: str):
    """Map a sort key to an ORDER BY clause, defaulting to newest-first.

    Built per call rather than held in a module-level dict — SQLAlchemy
    clause objects are not meant to be reused across statements.
    """
    if sort == SORT_NAME:
        return Product.name.asc()
    if sort == SORT_PRICE:
        return Product.price_cents.desc()
    return Product.created_at.desc()


class CatalogService:
    """Read-only queries over products and categories."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_products(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        category_id: uuid.UUID | None = None,
        sort: str = SORT_CREATED,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> ProductList:
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        page = max(page, 1)

        conditions = []
        if q:
            conditions.append(Product.name.ilike(f"%{q}%"))
        if status:
            conditions.append(Product.status == status)
        if category_id:
            conditions.append(Product.category_id == category_id)

        cols = select(*_PRODUCT_COLUMNS)
        count_stmt = select(func.count()).select_from(Product)
        for cond in conditions:
            cols = cols.where(cond)
            count_stmt = count_stmt.where(cond)

        total = (await self.db.execute(count_stmt)).scalar_one()

        # Tie-break on id so pagination is stable when the sort key repeats.
        stmt = (
            cols.order_by(_sort_clause(sort), Product.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).all()
        items = [ProductRead(**row._mapping) for row in rows]

        return ProductList(items=items, total=total, page=page, page_size=page_size)

    async def get_product(self, product_id: uuid.UUID) -> ProductRead | None:
        stmt = select(*_PRODUCT_COLUMNS).where(Product.id == product_id)
        row = (await self.db.execute(stmt)).first()
        return ProductRead(**row._mapping) if row else None

    async def list_categories(self) -> list[CategoryRead]:
        stmt = select(Category.id, Category.name, Category.slug).order_by(Category.name)
        rows = (await self.db.execute(stmt)).all()
        return [CategoryRead(**row._mapping) for row in rows]
