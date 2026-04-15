"""SQLAlchemy models for the users module."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi_users_db_sqlalchemy import (
    SQLAlchemyBaseUserTableUUID,
    SQLAlchemyUserDatabase,
)
from fastapi_users_db_sqlalchemy.access_token import (
    SQLAlchemyAccessTokenDatabase,
    SQLAlchemyBaseAccessTokenTable,
)
from fastapi_users_db_sqlalchemy.generics import GUID
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

Base = create_module_base("users")


class User(SQLAlchemyBaseUserTableUUID, Base, AuditMixin):  # ty: ignore[unsupported-base]
    """Local user (replaces Keycloak subject)."""

    __tablename__ = "users_user"

    # Inherited from SQLAlchemyBaseUserTableUUID:
    #   id (UUID PK), email, hashed_password, is_active, is_superuser, is_verified

    full_name: Mapped[str | None] = mapped_column(String(255), default=None)
    tenant_id: Mapped[str | None] = mapped_column(String(50), index=True, default=None)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, default=None
    )

    roles: Mapped[list[Role]] = relationship(
        secondary="users_user_role",
        lazy="noload",
        back_populates="users",
    )


class Role(Base, AuditMixin):  # ty: ignore[unsupported-base]
    """A named role that can hold a set of permission strings."""

    __tablename__ = "users_role"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), default=None)

    users: Mapped[list[User]] = relationship(
        secondary="users_user_role",
        lazy="noload",
        back_populates="roles",
    )


class UserRole(Base):  # ty: ignore[unsupported-base]
    """Association table between users and roles."""

    __tablename__ = "users_user_role"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users_user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users_role.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    assigned_by: Mapped[str | None] = mapped_column(String(255), default=None)


class UserAccessToken(SQLAlchemyBaseAccessTokenTable[uuid.UUID], Base):  # ty: ignore[unsupported-base]
    """fastapi-users DatabaseStrategy-backed access tokens."""

    __tablename__ = "users_access_token"

    # Inherited from SQLAlchemyBaseAccessTokenTable:
    #   token (str PK), created_at

    # Override the default `user_id` FK from the base class which points at
    # "user.id". We redirect it to "users_user.id" with ON DELETE CASCADE.
    # The base class uses @declared_attr, so we also use @declared_attr to
    # override it correctly.
    @declared_attr  # type: ignore[override]
    def user_id(self) -> Mapped[uuid.UUID]:
        return mapped_column(
            GUID,
            ForeignKey("users_user.id", ondelete="CASCADE"),
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
