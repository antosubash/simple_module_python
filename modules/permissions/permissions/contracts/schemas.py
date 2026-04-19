"""SQLModel DTOs for the Permissions module."""

from __future__ import annotations

import uuid

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel


class PermissionGroupOut(SQLModel):
    """A named group of related permission keys (one per module)."""

    name: str
    permissions: list[str]


class RoleOut(SQLModel):
    """A role as surfaced by the permissions admin UI."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None


class RolePermissionsOut(SQLModel):
    """A role together with its currently assigned permission keys."""

    role: RoleOut
    permissions: list[str]


class RolePermissionsUpdate(SQLModel):
    """Replace the full set of permission keys assigned to a role."""

    permissions: list[str] = Field(default_factory=list)
