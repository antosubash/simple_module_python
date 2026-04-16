"""SQLModel tables for the users module.

The ``User`` and ``UserAccessToken`` tables provide the exact column surface
that fastapi-users' database adapters
(:class:`fastapi_users_db_sqlalchemy.SQLAlchemyUserDatabase` and
:class:`fastapi_users_db_sqlalchemy.access_token.SQLAlchemyAccessTokenDatabase`)
introspect at runtime, so we don't need to inherit from their provided base
classes — we just declare equivalent columns directly on SQLModel tables.

The ``GUID`` type decorator and ``now_utc`` helper are imported from
``fastapi_users_db_sqlalchemy.generics`` because they are plain type
decorators / utility functions, not inheritance-based classes.
"""

# NOTE: intentionally no ``from __future__ import annotations`` — SQLModel
# Relationship resolution requires runtime annotations (not stringified ones)
# for forward references like ``list["Role"]`` to work correctly.

import uuid
from datetime import datetime

from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from fastapi_users_db_sqlalchemy.generics import GUID, TIMESTAMPAware, now_utc
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlalchemy import DateTime
from sqlmodel import Field, Relationship

Base = create_module_base("users")


class UserRole(Base, table=True):  # ty: ignore[unsupported-base]
    """Association table between users and roles."""

    __tablename__ = "users_user_role"

    user_id: uuid.UUID = Field(
        sa_type=GUID,
        foreign_key="users_user.id",
        ondelete="CASCADE",
        primary_key=True,
    )
    role_id: uuid.UUID = Field(
        sa_type=GUID,
        foreign_key="users_role.id",
        ondelete="CASCADE",
        primary_key=True,
    )
    assigned_at: datetime = Field(
        default_factory=now_utc,
        sa_type=DateTime(timezone=True),  # ty:ignore[invalid-argument-type]
        nullable=False,
    )
    assigned_by: str | None = Field(default=None, max_length=255)


class User(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """Local user (replaces Keycloak subject).

    Column surface mirrors :class:`fastapi_users_db_sqlalchemy.SQLAlchemyBaseUserTableUUID`
    so the fastapi-users adapters work unchanged.
    """

    __tablename__ = "users_user"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_type=GUID,
        primary_key=True,
    )
    email: str = Field(
        max_length=320,
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: str = Field(max_length=1024, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    is_superuser: bool = Field(default=False, nullable=False)
    is_verified: bool = Field(default=False, nullable=False)

    full_name: str | None = Field(default=None, max_length=255)
    tenant_id: str | None = Field(default=None, max_length=50, index=True)
    disabled_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # ty:ignore[invalid-argument-type]
        nullable=True,
    )
    last_login_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # ty:ignore[invalid-argument-type]
        index=True,
        nullable=True,
    )

    roles: list["Role"] = Relationship(
        link_model=UserRole,
        back_populates="users",
        sa_relationship_kwargs={"lazy": "noload"},
    )


class Role(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """A named role that can hold a set of permission strings."""

    __tablename__ = "users_role"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_type=GUID,
        primary_key=True,
    )
    name: str = Field(
        max_length=64,
        unique=True,
        index=True,
        nullable=False,
    )
    description: str | None = Field(default=None, max_length=255)

    users: list[User] = Relationship(
        link_model=UserRole,
        back_populates="roles",
        sa_relationship_kwargs={"lazy": "noload"},
    )


class UserAccessToken(Base, table=True):  # ty: ignore[unsupported-base]
    """fastapi-users DatabaseStrategy-backed access tokens.

    Column surface mirrors
    :class:`fastapi_users_db_sqlalchemy.access_token.SQLAlchemyBaseAccessTokenTableUUID`.
    """

    __tablename__ = "users_access_token"

    token: str = Field(max_length=43, primary_key=True)
    created_at: datetime = Field(
        default_factory=now_utc,
        sa_type=TIMESTAMPAware(timezone=True),  # ty:ignore[invalid-argument-type]
        index=True,
        nullable=False,
    )
    user_id: uuid.UUID = Field(
        sa_type=GUID,
        foreign_key="users_user.id",
        ondelete="CASCADE",
        nullable=False,
    )


__all__ = [
    "Base",
    "Role",
    "SQLAlchemyAccessTokenDatabase",
    "SQLAlchemyUserDatabase",
    "User",
    "UserAccessToken",
    "UserRole",
]
