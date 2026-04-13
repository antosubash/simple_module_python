"""Pydantic DTOs for the Products module."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductOut(BaseModel):
    """Product data returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    price: Decimal
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProductCreate(BaseModel):
    """Data required to create a new product."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    price: Decimal = Field(gt=0, decimal_places=2)


class ProductUpdate(BaseModel):
    """Data to update an existing product. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    is_active: bool | None = None
