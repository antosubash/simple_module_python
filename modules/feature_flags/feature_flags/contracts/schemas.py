"""SQLModel DTOs for the feature_flags module."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel


class FeatureFlagOverrideOut(SQLModel):
    """Stored override row as returned by the service/API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FeatureFlagView(SQLModel):
    """A flag as shown in the admin UI.

    Combines the in-code definition (from ``FeatureFlagRegistry``) with the
    persisted override (from the DB) so the UI can distinguish a flag that
    runs on its default from one that an admin has manually overridden.
    """

    name: str
    description: str = ""
    default_enabled: bool
    enabled: bool
    overridden: bool


class ToggleRequest(SQLModel):
    """Body for PUT /api/feature_flags/{name} — sets an override."""

    enabled: bool = Field(...)
