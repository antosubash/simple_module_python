"""Public request/response schemas for the users module."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi_users.schemas import CreateUpdateDictModel
from pydantic import ConfigDict, EmailStr
from sqlmodel import SQLModel

# NOTE on EmailStr: only *input* schemas (UserCreate/UserUpdate/UserInvite) use
# EmailStr — that is where an email must be format-validated. Response schemas
# (UserRead/UserListItem) use plain ``str``: their data comes straight from the
# DB (already validated on write), and FastAPI's response_model would otherwise
# re-run email-validator for every serialized user. Under load that validation
# was ~8% of total CPU on list endpoints (20 users/page) — pure waste.


class UserRead(CreateUpdateDictModel, SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False
    is_external: bool = False
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


class UserBulkInvite(SQLModel):
    """Invite several addresses in one submit, all sharing the same roles."""

    emails: list[EmailStr]
    role_names: list[str] = []


class BulkInviteResult(SQLModel):
    """Outcome for a single address in a bulk invite.

    Per-address rather than all-or-nothing: one already-registered address in
    a pasted list of twenty should not discard the other nineteen.
    """

    email: str
    status: str
    """``"sent"`` — mail dispatched. ``"link"`` — created, but the configured
    mailer cannot deliver, so ``link`` carries the URL. ``"failed"`` — see
    ``detail``."""
    detail: str = ""
    link: str | None = None
    """One-time accept URL. Populated only when the mailer cannot deliver;
    otherwise the token stays out of the response entirely."""


class BulkInviteResponse(SQLModel):
    results: list[BulkInviteResult]


class UserAdminCreate(SQLModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    role_names: list[str] = []


class UserDetailsUpdate(SQLModel):
    email: EmailStr
    full_name: str | None = None


class UserListItem(SQLModel):
    id: uuid.UUID
    email: str
    full_name: str | None = None
    is_active: bool
    is_verified: bool
    is_external: bool = False
    disabled_at: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime | None = None
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
