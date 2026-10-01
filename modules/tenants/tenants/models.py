"""SQLModel tables for the Tenants module.

None of these use ``MultiTenantMixin``: they *are* the tenant registry, and
the queries that matter ("which tenants am I in", "which invitation is this
token") span tenants by nature. Each carries an explicit ``tenant_id`` column
and every service method filters on it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from simple_module_db import is_valid_tenant_id
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlalchemy import Column, DateTime, Index, UniqueConstraint, text
from sqlalchemy.orm import validates
from sqlmodel import Field

from tenants.constants import (
    MAX_EMAIL_LEN,
    MAX_NAME_LEN,
    MAX_SLUG_LEN,
    TENANT_ID_LEN,
    MembershipRole,
    TenantStatus,
)

Base = create_module_base("tenants")


def _new_tenant_id() -> str:
    return uuid.uuid4().hex


class Tenant(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """An organisation. Its ``id`` is the value stored in every ``tenant_id``."""

    __tablename__ = "tenants_tenant"

    id: str = Field(default_factory=_new_tenant_id, primary_key=True, max_length=TENANT_ID_LEN)
    slug: str = Field(max_length=MAX_SLUG_LEN, unique=True, index=True)
    name: str = Field(max_length=MAX_NAME_LEN)
    status: str = Field(default=TenantStatus.ACTIVE, max_length=20, index=True)

    @validates("id")
    def _check_id(self, _key: str, value: str) -> str:
        # Refuses the reserved ``PLATFORM_TENANT_ID`` (and any malformed id):
        # a tenant with that id would own every platform file.
        if not is_valid_tenant_id(value):
            raise ValueError(f"{value!r} cannot be a tenant id")
        return value


class Membership(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """A user's membership in a tenant, with their role there.

    ``user_id`` is a plain string, not a foreign key: principals may come from
    an external identity provider (keycloak) with no local users row.
    """

    __tablename__ = "tenants_membership"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenants_membership_tenant_user"),
        Index("ix_tenants_membership_user", "user_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = Field(
        foreign_key="tenants_tenant.id", max_length=TENANT_ID_LEN, ondelete="CASCADE"
    )
    user_id: str = Field(max_length=64)
    role: str = Field(default=MembershipRole.MEMBER, max_length=20)
    # Snapshot of the principal's email when they joined, for display only —
    # there is no provider-agnostic user lookup (keycloak users are not local).
    email: str | None = Field(default=None, max_length=MAX_EMAIL_LEN)


class Invitation(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """A pending invitation. Only the token's SHA-256 is stored."""

    __tablename__ = "tenants_invitation"
    __table_args__ = (
        # One open invitation per address: the service's duplicate check is a
        # read, so concurrent requests need the database to say no (SQLite
        # has no row lock to serialise them). Expired rows are reaped by the
        # service before a re-invite, so only ``accepted_at`` is in the predicate.
        Index(
            "uq_tenants_invitation_open_email",
            "tenant_id",
            "email",
            unique=True,
            sqlite_where=text("accepted_at IS NULL"),
            postgresql_where=text("accepted_at IS NULL"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = Field(
        foreign_key="tenants_tenant.id", max_length=TENANT_ID_LEN, ondelete="CASCADE", index=True
    )
    email: str = Field(max_length=MAX_EMAIL_LEN)
    role: str = Field(default=MembershipRole.MEMBER, max_length=20)
    token_hash: str = Field(max_length=64, unique=True, index=True)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    accepted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
