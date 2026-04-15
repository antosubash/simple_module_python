"""Public request/response schemas for the users module."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi_users import schemas
from pydantic import BaseModel, EmailStr


# fastapi-users-provided base schemas
class UserRead(schemas.BaseUser[uuid.UUID]):
    full_name: str | None = None
    tenant_id: str | None = None
    disabled_at: datetime | None = None
    last_login_at: datetime | None = None


class UserCreate(schemas.BaseUserCreate):
    full_name: str | None = None


class UserUpdate(schemas.BaseUserUpdate):
    full_name: str | None = None


# Admin + invite + self profile
class UserInvite(BaseModel):
    email: EmailStr
    full_name: str | None = None
    role_names: list[str] = []


class UserListItem(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    is_active: bool
    is_verified: bool
    disabled_at: datetime | None = None
    last_login_at: datetime | None = None
    roles: list[str] = []


class RoleAssignment(BaseModel):
    role_names: list[str]


class AcceptInviteRequest(BaseModel):
    token: str
    password: str


class PasswordResetLink(BaseModel):
    link: str


class SelfProfileUpdate(BaseModel):
    full_name: str | None = None
