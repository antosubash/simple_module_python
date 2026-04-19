"""SQLModel DTOs for the Settings module."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel

from settings.constants import (
    DESCRIPTION_MAX_LENGTH,
    KEY_MAX_LENGTH,
    VALUE_MAX_LENGTH,
)


class SettingOut(SQLModel):
    """A setting returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    value: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SettingCreate(SQLModel):
    """Payload to create a new setting."""

    key: str = Field(min_length=1, max_length=KEY_MAX_LENGTH)
    value: str = Field(max_length=VALUE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)


class SettingUpdate(SQLModel):
    """Payload to update an existing setting. All fields optional."""

    value: str | None = Field(default=None, max_length=VALUE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)


class SettingUpsert(SQLModel):
    """Payload for upsert-by-key operations."""

    value: str = Field(max_length=VALUE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
