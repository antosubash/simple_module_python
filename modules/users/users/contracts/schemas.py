"""Public request/response schemas for the users module.

All DTOs are non-table SQLModel classes (SQLModel is the standard across the
project for every model, table or not). The user Read/Create/Update variants
re-implement the field surface fastapi-users expects on its router schemas
(via :class:`fastapi_users.schemas.BaseUser` et al.) plus the
``create_update_dict`` / ``create_update_dict_superuser`` methods its
user-manager calls at runtime.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import ConfigDict, EmailStr
from sqlmodel import SQLModel


class _CreateUpdateDictSQLModel(SQLModel):
    """SQLModel mixin providing fastapi-users' ``create_update_dict`` helpers."""

    def create_update_dict(self) -> dict:
        return self.model_dump(
            exclude_unset=True,
            exclude={"id", "is_superuser", "is_active", "is_verified", "oauth_accounts"},
        )

    def create_update_dict_superuser(self) -> dict:
        return self.model_dump(exclude_unset=True, exclude={"id"})


class UserRead(_CreateUpdateDictSQLModel):
    """User fields returned by fastapi-users' user router."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False
    full_name: str | None = None
    tenant_id: str | None = None
    disabled_at: datetime | None = None
    last_login_at: datetime | None = None


class UserCreate(_CreateUpdateDictSQLModel):
    """Fields accepted by fastapi-users' ``/register`` endpoint."""

    email: EmailStr
    password: str
    is_active: bool | None = True
    is_superuser: bool | None = False
    is_verified: bool | None = False
    full_name: str | None = None


class UserUpdate(_CreateUpdateDictSQLModel):
    """Fields accepted by fastapi-users' self-update and admin-update endpoints."""

    password: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
    is_verified: bool | None = None
    full_name: str | None = None


# Admin + invite + self profile
class UserInvite(SQLModel):
    email: EmailStr
    full_name: str | None = None
    role_names: list[str] = []


class UserListItem(SQLModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    is_active: bool
    is_verified: bool
    disabled_at: datetime | None = None
    last_login_at: datetime | None = None
    roles: list[str] = []


class RoleAssignment(SQLModel):
    role_names: list[str]


class AcceptInviteRequest(SQLModel):
    token: str
    password: str


class PasswordResetLink(SQLModel):
    link: str


class SelfProfileUpdate(SQLModel):
    full_name: str | None = None
