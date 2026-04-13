"""Products contracts — public interface for other modules."""

from sm_products.contracts.events import (
    ProductCreated,
    ProductDeleted,
    ProductUpdated,
)
from sm_products.contracts.schemas import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from sm_products.contracts.service import IProductService

__all__ = [
    "ProductCreate",
    "ProductCreated",
    "ProductDeleted",
    "ProductOut",
    "ProductUpdate",
    "ProductUpdated",
    "IProductService",
]
