"""Product service protocol — the public contract other modules depend on."""

from __future__ import annotations

from typing import Protocol

from products.contracts.schemas import ProductCreate, ProductOut, ProductUpdate


class IProductService(Protocol):
    """Interface for product operations."""

    async def get_all(self) -> list[ProductOut]: ...
    async def get_by_id(self, product_id: int) -> ProductOut | None: ...
    async def create(self, data: ProductCreate) -> ProductOut: ...
    async def update(self, product_id: int, data: ProductUpdate) -> ProductOut | None: ...
    async def delete(self, product_id: int) -> bool: ...
