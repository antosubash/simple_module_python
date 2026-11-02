"""The generic share table (GH #526)."""

from __future__ import annotations

import uuid
from datetime import datetime

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, MultiTenantMixin
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field

from sharing.constants import (
    IX_SHARE_RESOURCE,
    RESOURCE_ID_MAX,
    RESOURCE_TYPE_MAX,
    ROLE_MAX,
    SUBJECT_ID_MAX,
    SUBJECT_TYPE_MAX,
    SUBJECT_USER,
    TABLE_SHARE,
    UQ_SHARE,
)

Base = create_module_base("sharing")


class ResourceShare(Base, MultiTenantMixin, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """One subject's access to one resource.

    ``resource_id`` is the canonical text of the row's key (a UUID's ``hex``,
    an int's decimal), so the policy's ``EXISTS`` can compare it on any
    database. Revoking deletes the row; expiry is checked in SQL.
    """

    __tablename__ = TABLE_SHARE
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "resource_type", "resource_id", "subject_type", "subject_id", name=UQ_SHARE
        ),
        Index(IX_SHARE_RESOURCE, "tenant_id", "resource_type", "resource_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    resource_type: str = Field(max_length=RESOURCE_TYPE_MAX)
    resource_id: str = Field(max_length=RESOURCE_ID_MAX)
    subject_type: str = Field(default=SUBJECT_USER, max_length=SUBJECT_TYPE_MAX)
    subject_id: str = Field(max_length=SUBJECT_ID_MAX, index=True)
    role: str = Field(max_length=ROLE_MAX)
    granted_by: str = Field(max_length=SUBJECT_ID_MAX)
    expires_at: datetime | None = Field(default=None)
