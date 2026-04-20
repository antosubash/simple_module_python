"""SQLModel tables for the feature_flags module.

Stores persisted overrides for flags that modules declare via
``register_feature_flags``. The definition of a flag (name, description,
default) lives in code; this table only records admin-applied overrides so
they survive across app restarts.

A row's ``scope`` selects whether the override applies globally
(``system``, ``scope_id=""``) or to a single tenant (``tenant``,
``scope_id=<tenant_id>``). Resolution at runtime: tenant > system > default.
"""

from __future__ import annotations

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from feature_flags.constants import (
    SCOPE_ID_MAX_LENGTH,
    SCOPE_MAX_LENGTH,
    SCOPE_SYSTEM,
    SYSTEM_SCOPE_ID,
    TABLE_OVERRIDE,
    UQ_OVERRIDE_SCOPE_NAME,
)

Base = create_module_base("feature_flags")


class FeatureFlagOverride(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """Persisted override for a single feature flag at a given scope."""

    __tablename__ = TABLE_OVERRIDE
    __table_args__ = (UniqueConstraint("scope", "scope_id", "name", name=UQ_OVERRIDE_SCOPE_NAME),)

    id: int | None = Field(default=None, primary_key=True)
    scope: str = Field(default=SCOPE_SYSTEM, max_length=SCOPE_MAX_LENGTH, index=True)
    scope_id: str = Field(default=SYSTEM_SCOPE_ID, max_length=SCOPE_ID_MAX_LENGTH, index=True)
    name: str = Field(max_length=200, index=True)
    enabled: bool = Field(default=False)
