"""SQLModel tables for the Settings module."""

from __future__ import annotations

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlmodel import Field

# Provider is auto-detected from SM_DATABASE_URL (falls back to SQLite).
# On PostgreSQL this gives the module its own `settings` schema; on SQLite
# all modules share one schema, so __tablename__ is prefixed for isolation.
Base = create_module_base("settings")


class Setting(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """A setting entity."""

    __tablename__ = "settings_setting"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = Field(default=True)
