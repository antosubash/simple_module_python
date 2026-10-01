"""Public DTOs for the Tenants module."""

from __future__ import annotations

import re
from datetime import datetime

from email_validator import EmailNotValidError, validate_email
from pydantic import field_validator
from simple_module_db import PLATFORM_TENANT_ID
from sqlmodel import Field, SQLModel

from tenants.constants import MAX_EMAIL_LEN, MAX_NAME_LEN, MembershipRole

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?$")


class TenantCreate(SQLModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LEN)
    # Validated below: SQLModel's Field swallows a v1-style ``regex=`` without
    # enforcing it, and rejects pydantic v2's ``pattern=``.
    slug: str | None = Field(default=None)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("slug")
    @classmethod
    def _slug_shape(cls, value: str | None) -> str | None:
        if value is not None and not _SLUG_RE.fullmatch(value):
            raise ValueError("slug must be 1-50 lowercase letters, digits or inner dashes")
        if value == PLATFORM_TENANT_ID:
            raise ValueError(f"slug {value!r} is reserved")
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
        try:
            checked = validate_email(
                value.strip(), check_deliverability=False, test_environment=True
            )
        except EmailNotValidError as exc:
            raise ValueError("invalid email") from exc
        return checked.normalized.lower()

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
