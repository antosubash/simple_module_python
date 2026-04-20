"""Public request/response schemas for the users module."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi_users.schemas import CreateUpdateDictModel
from pydantic import ConfigDict, EmailStr
from sqlmodel import SQLModel


class UserRead(CreateUpdateDictModel, SQLModel):
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


class UserCreate(CreateUpdateDictModel, SQLModel):
    email: EmailStr
    password: str
    is_active: bool | None = True
    is_superuser: bool | None = False
    is_verified: bool | None = False
    full_name: str | None = None


class UserUpdate(CreateUpdateDictModel, SQLModel):
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


class RoleListItem(SQLModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    user_count: int = 0


class RoleAssignment(SQLModel):
    role_names: list[str]


class AcceptInviteRequest(SQLModel):
    token: str
    password: str


class PasswordResetLink(SQLModel):
    link: str


class SelfProfileUpdate(SQLModel):
    full_name: str | None = None
