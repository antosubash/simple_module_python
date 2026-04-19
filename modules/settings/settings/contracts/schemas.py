"""SQLModel DTOs for the Settings module."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel


class SettingOut(SQLModel):
    """Setting data returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SettingCreate(SQLModel):
    """Data required to create a new setting."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class SettingUpdate(SQLModel):
    """Data to update an existing setting. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None
