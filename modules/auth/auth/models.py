"""Short-lived cross-worker outcomes for browser token renewal."""

from typing import Any

from simple_module_db.base import create_module_base
from sqlalchemy import JSON
from sqlmodel import Field

Base = create_module_base("auth")


class RefreshOutcome(Base, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "auth_refresh_outcome"

    session_id: str = Field(primary_key=True, max_length=128)
    expires_at: int = Field(index=True)
    session: dict[str, Any] = Field(sa_type=JSON)
