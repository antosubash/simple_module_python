"""Access-token table backing fastapi-users' DatabaseStrategy.

Column surface mirrors fastapi-users' ``SQLAlchemyBaseAccessTokenTableUUID``
so the ``SQLAlchemyAccessTokenDatabase`` adapter binds to it without
inheriting from the upstream base class.
"""

import uuid
from datetime import datetime

from fastapi_users_db_sqlalchemy.generics import GUID, TIMESTAMPAware, now_utc
from sqlmodel import Field

from users.models._base import Base


class UserAccessToken(Base, table=True):  # ty: ignore[unsupported-base]
    """fastapi-users DatabaseStrategy-backed access tokens."""

    __tablename__ = "users_access_token"

    token: str = Field(max_length=43, primary_key=True)
    created_at: datetime = Field(
        default_factory=now_utc,
        sa_type=TIMESTAMPAware(timezone=True),
        index=True,
    )
    user_id: uuid.UUID = Field(
        sa_type=GUID,
        foreign_key="users_user.id",
        ondelete="CASCADE",
        index=True,  # PostgreSQL does not auto-index FKs
    )
