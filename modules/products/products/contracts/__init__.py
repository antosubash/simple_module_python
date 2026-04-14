"""Products contracts — public interface for other modules."""

from products.contracts.schemas import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from products.contracts.service import IProductService

__all__ = ["ProductCreate", "ProductOut", "ProductUpdate", "IProductService"]
