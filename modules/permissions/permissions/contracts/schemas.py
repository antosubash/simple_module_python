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


class UserOut(SQLModel):
    """A user as surfaced by the permissions admin UI."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None = None


class UserPermissionsOut(SQLModel):
    """A user together with their direct and role-inherited permission keys."""

    user: UserOut
    roles: list[str]
    direct: list[str]
    """Keys granted directly to this user."""
    inherited: list[str]
    """Keys the user holds via any of their roles (excluding duplicates of ``direct``)."""


class UserPermissionsUpdate(SQLModel):
    """Replace the full set of permission keys granted directly to a user."""

    permissions: list[str] = Field(default_factory=list)
