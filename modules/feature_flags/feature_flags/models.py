"""SQLModel tables for the feature_flags module.

Stores persisted overrides for flags that modules declare via
``register_feature_flags``. The definition of a flag (name, description,
default) lives in code; this table only records admin-applied overrides so
they survive across app restarts.
"""

from __future__ import annotations

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from feature_flags.constants import TABLE_OVERRIDE, UQ_OVERRIDE_NAME

Base = create_module_base("feature_flags")


class FeatureFlagOverride(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """Persisted override for a single feature flag."""

    __tablename__ = TABLE_OVERRIDE
    __table_args__ = (UniqueConstraint("name", name=UQ_OVERRIDE_NAME),)

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200, index=True)
    enabled: bool = Field(default=False)
