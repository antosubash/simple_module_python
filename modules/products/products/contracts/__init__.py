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

__all__ = [
    "ProductCreate",
    "ProductCreated",
    "ProductDeleted",
    "ProductOut",
    "ProductUpdate",
    "ProductUpdated",
]
