"""SQLModel DTOs for the Products module.

These are non-table SQLModel classes (no ``table=True``) — they are Pydantic
models with SQLModel's ``Field`` for validation, usable as FastAPI request
and response bodies. ``model_config = ConfigDict(from_attributes=True)``
enables ``ProductOut.model_validate(orm_row)`` against ORM instances.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel


class ProductOut(SQLModel):
    """Product data returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    price: Decimal
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProductCreate(SQLModel):
    """Data required to create a new product."""

    name: str = Field(min_length=1, max_length=200, description="Product name is required")
    description: str | None = Field(default=None, max_length=2000)
    price: Decimal = Field(gt=0, decimal_places=2, description="Price must be greater than 0")


class ProductUpdate(SQLModel):
    """Data to update an existing product. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    is_active: bool | None = None
