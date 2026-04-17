"""Association table linking users and roles."""

import uuid
from datetime import datetime

from fastapi_users_db_sqlalchemy.generics import GUID, now_utc
from sqlalchemy import DateTime, Index
from sqlmodel import Field

from users.models._base import Base


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
        sa_type=DateTime(timezone=True),
    )
    assigned_by: str | None = Field(default=None, max_length=255)

    # The composite PK covers ``user_id``-first lookups; add a standalone
    # index on ``role_id`` for reverse lookups — PostgreSQL does not
    # auto-index FKs.
    __table_args__ = (Index("ix_users_user_role_role_id", "role_id"),)
