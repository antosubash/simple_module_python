"""Refresh token for mobile/API bearer auth."""

from __future__ import annotations

import uuid as uuid_mod
from datetime import UTC, datetime

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlmodel import Field

from users.models._base import Base


class RefreshToken(Base, table=True):  # ty: ignore[unsupported-base]
    """Opaque refresh token exchanged for a new access + refresh pair."""

    __tablename__ = "users_refresh_token"

    token: uuid_mod.UUID = Field(default_factory=uuid_mod.uuid4, primary_key=True)
    # ``sa_type=GUID`` to match ``User.id``, not SQLModel's default ``Uuid``.
    # The two render identically on Postgres (UUID) but not on SQLite, where
    # ``Uuid`` stores the bare hex and ``GUID`` the dashed form — so the FK
    # never matched a parent row and any SQL join across it returned nothing.
    # Invisible until ``PRAGMA foreign_keys=ON`` (GH #339).
    user_id: uuid_mod.UUID = Field(sa_type=GUID, foreign_key="users_user.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    revoked_at: datetime | None = None
