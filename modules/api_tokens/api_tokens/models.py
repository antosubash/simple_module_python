"""SQLModel tables for the api_tokens module.

One table holds both credential kinds. Only ``sha256(token)`` is stored; the
secret itself is shown once, in the response that created it, and nowhere
else. ``prefix`` is a short, non-secret slice so a person can tell their
tokens apart in a list.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import ClassVar

import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import GUID
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, MultiTenantMixin
from simple_module_db.types import AwareDateTime
from sqlalchemy import Index
from sqlmodel import Field

from api_tokens.constants import IX_TOKEN_HASH, NAME_MAX_LENGTH, TABLE_TOKEN, TokenKind

Base = create_module_base("api_tokens")


class ApiToken(Base, AuditMixin, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    """A personal access token or a service API key."""

    __tablename__ = TABLE_TOKEN
    # The hash is a credential-equivalent lookup key and ``last_used_at`` is
    # bumped by a Core UPDATE that never reaches the audit listener anyway;
    # neither belongs in the audit trail. Create and revoke still do.
    __audit_exclude_fields__: ClassVar[set[str]] = {"token_hash", "last_used_at"}
    # ``token_hash`` leads, so the per-request lookup by hash alone is an
    # index seek; ``tenant_id`` is in the key because every unique key on a
    # tenant-scoped table must be (SM024). A SHA-256 of 32 random bytes does
    # not collide, so the wider key loses nothing.
    __table_args__ = (Index(IX_TOKEN_HASH, "token_hash", "tenant_id", unique=True),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    kind: str = Field(max_length=16, default=TokenKind.PERSONAL)
    name: str = Field(max_length=NAME_MAX_LENGTH)
    prefix: str = Field(max_length=16)
    # Looked up before any tenant is known — see ``__table_args__``.
    token_hash: str = Field(max_length=64)
    # ``GUID``, the type ``users_user.id`` has, so the values compare equal on
    # SQLite too (``sa.Uuid`` stores bare hex there — GH #339). No foreign key:
    # every module owns its own ``MetaData``, so one cannot name another
    # module's table. A deleted owner is handled where it matters — the
    # resolver finds no account and refuses the token.
    owner_user_id: uuid.UUID | None = Field(default=None, sa_type=GUID, index=True)
    scopes: list[str] = Field(default_factory=list, sa_type=sa.JSON())
    roles: list[str] = Field(default_factory=list, sa_type=sa.JSON())
    expires_at: datetime = Field(sa_type=AwareDateTime())
    last_used_at: datetime | None = Field(default=None, sa_type=AwareDateTime())
    revoked_at: datetime | None = Field(default=None, sa_type=AwareDateTime())
