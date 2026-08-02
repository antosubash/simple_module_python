"""SQLModel DTOs for the Catalog module."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel


class CatalogOut(SQLModel):
    """Catalog data returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CatalogCreate(SQLModel):
    """Data required to create a new catalog."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class CatalogUpdate(SQLModel):
    """Data to update an existing catalog. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None
