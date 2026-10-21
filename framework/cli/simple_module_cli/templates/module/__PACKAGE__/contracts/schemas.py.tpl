"""SQLModel DTOs for the {{MODULE_NAME}} module."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, field_validator
from sqlmodel import Field, SQLModel

from {{PACKAGE_NAME}}.constants import DESCRIPTION_MAX_LENGTH, NAME_MAX_LENGTH


class {{SINGULAR_CLASS}}Out(SQLModel):
    """{{SINGULAR_CLASS}} data returned by the API."""

    model_config = ConfigDict(from_attributes=True)  # ty: ignore[invalid-assignment]

    id: int
    name: str
    description: str | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class {{SINGULAR_CLASS}}Create(SQLModel):
    """Data required to create a new {{SINGULAR}}."""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)


class {{SINGULAR_CLASS}}Update(SQLModel):
    """Data to update an existing {{SINGULAR}}. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    is_active: bool | None = None

    @field_validator("name", "is_active", mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: object) -> object:
        """Omitted means unchanged; an explicit null would hit a NOT NULL column."""
        if value is None:
            raise ValueError("must not be null")
        return value
