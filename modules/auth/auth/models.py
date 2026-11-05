"""Short-lived cross-worker outcomes for browser token renewal."""

from typing import Any, ClassVar

from simple_module_db.base import create_module_base
from sqlalchemy import JSON, BigInteger
from sqlmodel import Field

Base = create_module_base("auth")


class RefreshOutcome(Base, table=True):  # ty: ignore[unsupported-base]
    __audit_redact_fields__: ClassVar[set[str]] = {"outcome_key", "lock_key", "session"}

    __tablename__ = "auth_refresh_outcome"

    # sha256(refresh key : identity : spent sealed token); not a session id.
    outcome_key: str = Field(primary_key=True, max_length=128)
    # sha256(refresh key : identity), the per-session lock; logout deletes by it.
    lock_key: str = Field(index=True, max_length=128)
    # BIGINT: a 32-bit Unix time overflows in 2038.
    expires_at: int = Field(sa_type=BigInteger, index=True)
    session: dict[str, Any] = Field(sa_type=JSON)
