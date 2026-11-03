"""OIDC user cache -- maps a provider subject to a stable framework UUID."""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime

from simple_module_db.base import create_module_base
from simple_module_db.types import AwareDateTime
from sqlalchemy import UniqueConstraint
from sqlmodel import Field

Base = create_module_base("oidc")


class OidcUserCache(Base, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "oidc_user_cache"

    id: uuid_mod.UUID = Field(default_factory=uuid_mod.uuid4, primary_key=True)
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_oidc_user_cache_issuer_subject"),
    )

    issuer: str
    subject: str
    email: str = ""
    full_name: str | None = None
    last_login_at: datetime | None = Field(default=None, sa_type=AwareDateTime())
