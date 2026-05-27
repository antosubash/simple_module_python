"""SQLModel table for the Audit Log module."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from simple_module_db.base import create_module_base
from sqlalchemy import JSON, DateTime, Index, func
from sqlmodel import Column, Field

from audit_log.constants import (
    ACTION_MAX_LENGTH,
    CORRELATION_ID_MAX_LENGTH,
    ENTITY_ID_MAX_LENGTH,
    ENTITY_TYPE_MAX_LENGTH,
    MODULE_PACKAGE,
    TABLE_AUDIT_ENTRY,
    USER_ID_MAX_LENGTH,
)

Base = create_module_base(MODULE_PACKAGE)


class AuditEntry(Base, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = TABLE_AUDIT_ENTRY
    __audit_exclude__ = True

    __table_args__ = (
        Index("ix_audit_entry_entity_type", "entity_type"),
        Index("ix_audit_entry_entity_id", "entity_id"),
        Index("ix_audit_entry_user_id", "user_id"),
        Index("ix_audit_entry_created_at", "created_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entity_type: str = Field(max_length=ENTITY_TYPE_MAX_LENGTH)
    entity_id: str = Field(max_length=ENTITY_ID_MAX_LENGTH)
    action: str = Field(max_length=ACTION_MAX_LENGTH)
    changes: dict | list = Field(default_factory=list, sa_column=Column(JSON))
    user_id: str | None = Field(default=None, max_length=USER_ID_MAX_LENGTH)
    correlation_id: str | None = Field(default=None, max_length=CORRELATION_ID_MAX_LENGTH)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
    )
