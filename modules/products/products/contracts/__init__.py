"""Products contracts — public interface for other modules."""

from products.contracts.events import (
    ProductCreated,
    ProductDeleted,
    ProductUpdated,
)
from products.contracts.schemas import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from products.contracts.service import IProductService

__all__ = [
    "IProductService",
    "ProductCreate",
    "ProductCreated",
    "ProductDeleted",
    "ProductOut",
    "ProductUpdate",
    "ProductUpdated",
]
