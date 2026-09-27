"""Public DTOs for the Tenants module."""

from __future__ import annotations

from datetime import datetime

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from tenants.constants import MAX_EMAIL_LEN, MAX_NAME_LEN, MembershipRole

_SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?$"


class TenantCreate(SQLModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LEN)
    slug: str | None = Field(default=None, regex=_SLUG_PATTERN)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class TenantView(SQLModel):
    id: str
    slug: str
    name: str
    status: str
    created_at: datetime | None = None


class MyTenantView(TenantView):
    """A tenant as seen by one of its members."""

    role: str


class MemberView(SQLModel):
    user_id: str
    email: str | None = None
    role: str
    joined_at: datetime | None = None


class RoleChange(SQLModel):
    role: MembershipRole


class InvitationCreate(SQLModel):
    email: str = Field(min_length=3, max_length=MAX_EMAIL_LEN)
    role: MembershipRole = MembershipRole.MEMBER

    @field_validator("email")
    @classmethod
    def _normalise(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value:
            raise ValueError("invalid email")
        return value

    @field_validator("role")
    @classmethod
    def _no_owner_invites(cls, value: MembershipRole) -> MembershipRole:
        # Ownership is transferred by an owner on an existing member, never
        # handed to whoever holds a link.
        if value == MembershipRole.OWNER:
            raise ValueError("invitations cannot grant the owner role")
        return value


class InvitationView(SQLModel):
    id: int
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None = None


class InvitationIssued(InvitationView):
    """Returned once, at creation — the only time the raw token exists."""

    token: str
    accept_url: str


class InvitationPreview(SQLModel):
    tenant_name: str
    email: str
    role: str
    expired: bool
    accepted: bool


class ActiveTenant(SQLModel):
    """The ``tenant`` shared Inertia prop."""

    active: MyTenantView | None = None
    memberships: list[MyTenantView] = []
    suspended: bool = False
