"""SQLModel DTOs for the Catalog module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import SQLModel


class CategoryRead(SQLModel):
    """A category as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str


class ProductRead(SQLModel):
    """A product as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    name: str
    description: str
    status: str
    price_cents: int
    category_id: uuid.UUID
    created_at: datetime


class ProductList(SQLModel):
    """A page of products plus the total matching the same filters."""

    items: list[ProductRead]
    total: int
    page: int
    page_size: int
