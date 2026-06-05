"""OIDC user cache -- maps a provider subject to a stable framework UUID."""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime

from simple_module_db.base import create_module_base
from sqlmodel import Field

Base = create_module_base("oidc")


class OidcUserCache(Base, table=True):
    __tablename__ = "oidc_user_cache"

    id: uuid_mod.UUID = Field(default_factory=uuid_mod.uuid4, primary_key=True)
    subject: str = Field(unique=True, index=True)
    email: str = ""
    full_name: str | None = None
    last_login_at: datetime | None = None
