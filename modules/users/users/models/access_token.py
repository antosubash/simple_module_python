"""Access-token table backing fastapi-users' DatabaseStrategy.

Column surface mirrors fastapi-users' ``SQLAlchemyBaseAccessTokenTableUUID``
so the ``SQLAlchemyAccessTokenDatabase`` adapter binds to it without
inheriting from the upstream base class.
"""

import uuid
from datetime import datetime, timedelta

from fastapi_users_db_sqlalchemy.generics import GUID, TIMESTAMPAware, now_utc
from sqlmodel import Field

from users.models._base import Base

_FALLBACK_LIFETIME = timedelta(days=30)
"""Deadline for a row minted without one — the old process-wide ceiling.

Only reachable if a caller builds the model directly instead of going through
``ExpiringDatabaseStrategy`` or ``_create_token_pair``. Defaulting to the widest
window the deployment ever accepted keeps that path no worse than it used to be
rather than silently minting a credential that never expires.
"""


def _default_expires_at() -> datetime:
    return now_utc() + _FALLBACK_LIFETIME


class UserAccessToken(Base, table=True):  # ty: ignore[unsupported-base]
    """fastapi-users DatabaseStrategy-backed access tokens."""

    __tablename__ = "users_access_token"

    token: str = Field(max_length=43, primary_key=True)
    created_at: datetime = Field(
        default_factory=now_utc,
        sa_type=TIMESTAMPAware(timezone=True),
        index=True,
    )
    expires_at: datetime = Field(
        default_factory=_default_expires_at,
        sa_type=TIMESTAMPAware(timezone=True),
        index=True,
    )
    """When this particular row stops authenticating.

    Per row rather than one constant for the process, because the credentials
    minted here do not all mean the same thing: ``/auth/token`` promises fifteen
    minutes in its own ``expires_in``, an ordinary sign-in writes a fourteen-day
    ``sm_auth`` cookie, and "keep me signed in" asks for thirty days. Reading all
    three back against a single thirty-day window meant a cookie lifted off disk
    stayed replayable for a month whatever it had been issued for.
    """

    session_version: int = Field(default=0)
    """``User.session_version`` at mint time; a mismatch means this is stranded.

    The bearer half of what the session cookie does by stamping the counter into
    its payload. Without it a password change bumped the counter, stranded every
    session, and left every bearer token minted before it working — including the
    ones an attacker who knew the old password had already collected.
    """
    user_id: uuid.UUID = Field(
        sa_type=GUID,
        foreign_key="users_user.id",
        ondelete="CASCADE",
        index=True,  # PostgreSQL does not auto-index FKs
    )
