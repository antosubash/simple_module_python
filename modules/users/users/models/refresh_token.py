"""Refresh token for mobile/API bearer auth."""

from __future__ import annotations

import uuid as uuid_mod
from datetime import UTC, datetime

from sqlmodel import Field

from users.models._base import Base


class RefreshToken(Base, table=True):  # ty: ignore[unsupported-base]
    """Opaque refresh token exchanged for a new access + refresh pair."""

    __tablename__ = "users_refresh_token"

    token: uuid_mod.UUID = Field(default_factory=uuid_mod.uuid4, primary_key=True)
    user_id: uuid_mod.UUID = Field(foreign_key="users_user.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    revoked_at: datetime | None = None
