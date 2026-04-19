"""SQLModel DTOs for the feature_flags module."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel


class FeatureFlagOverrideOut(SQLModel):
    """Stored override row as returned by the service/API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    scope: str
    scope_id: str
    name: str
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FeatureFlagView(SQLModel):
    """A flag as shown in the admin UI for a given scope.

    ``enabled`` is the value an ``is_enabled(name, tenant_id=...)`` call
    would return for this scope. ``overridden`` reports whether the row
    that produced ``enabled`` lives at *this* scope (vs. inherited from
    system or default). ``system_enabled`` exposes the underlying system
    value when viewing a tenant scope, so the UI can show "inheriting:
    on/off" next to the toggle.
    """

    name: str
    description: str = ""
    default_enabled: bool
    enabled: bool
    overridden: bool
    # Only populated when listing under a tenant scope; helps the UI render
    # what would happen if the tenant override were cleared.
    system_enabled: bool | None = None


class ToggleRequest(SQLModel):
    """Body for PUT /api/feature_flags/[tenant/{tenant_id}/]{name} — sets an override."""

    enabled: bool = Field(...)
