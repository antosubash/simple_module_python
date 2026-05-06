"""OAuth account table — links a (provider, account_id) pair to a User row.

Column surface mirrors fastapi-users' ``SQLAlchemyBaseOAuthAccountTableUUID``
so ``SQLAlchemyUserDatabase`` binds to it without inheriting from the upstream
base class (whose ``Mapped[...]`` columns are incompatible with SQLModel's
metaclass — same constraint as ``User`` / ``UserAccessToken``).
"""

# NOTE: intentionally no ``from __future__ import annotations`` — SQLModel
# Relationship resolution requires runtime annotations.

import uuid

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlmodel import Field

from users.models._base import Base


class OAuthAccount(Base, table=True):  # ty: ignore[unsupported-base]
    """One row per (provider, account_id) link to a local User."""

    __tablename__ = "users_oauth_account"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_type=GUID,
        primary_key=True,
    )
    user_id: uuid.UUID = Field(
        sa_type=GUID,
        foreign_key="users_user.id",
        ondelete="CASCADE",
        index=True,
    )
    oauth_name: str = Field(max_length=100, index=True)
    access_token: str = Field(max_length=1024)
    expires_at: int | None = Field(default=None)
    refresh_token: str | None = Field(default=None, max_length=1024)
    account_id: str = Field(max_length=320, index=True)
    account_email: str = Field(max_length=320)
