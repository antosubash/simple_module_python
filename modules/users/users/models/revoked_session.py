"""Per-browser session retirement records."""

import uuid
from datetime import datetime

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlmodel import Field

from users.models._base import Base


class RevokedSession(Base, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "users_revoked_session"

    session_id: str = Field(primary_key=True, max_length=64)
    user_id: uuid.UUID = Field(
        sa_type=GUID, foreign_key="users_user.id", ondelete="CASCADE", index=True
    )
    expires_at: datetime = Field(index=True)
