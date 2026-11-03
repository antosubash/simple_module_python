"""Short-lived cross-worker outcomes for browser token renewal."""

from typing import Any

from simple_module_db.base import create_module_base
from sqlalchemy import JSON, BigInteger
from sqlmodel import Field

Base = create_module_base("auth")


class RefreshOutcome(Base, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "auth_refresh_outcome"

    session_id: str = Field(primary_key=True, max_length=128)
    # BIGINT: a 32-bit Unix time overflows in 2038.
    expires_at: int = Field(sa_type=BigInteger, index=True)
    session: dict[str, Any] = Field(sa_type=JSON)
