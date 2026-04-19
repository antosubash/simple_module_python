"""SQLModel tables for the Settings module."""

from __future__ import annotations

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from settings.constants import (
    DESCRIPTION_MAX_LENGTH,
    KEY_MAX_LENGTH,
    MODULE_PACKAGE,
    SCOPE_ID_MAX_LENGTH,
    SCOPE_MAX_LENGTH,
    SCOPE_SYSTEM,
    SYSTEM_SCOPE_ID,
    TABLE_SETTING,
    UQ_SCOPE_KEY,
    VALUE_MAX_LENGTH,
)

Base = create_module_base(MODULE_PACKAGE)


class Setting(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """A key/value configuration entry scoped to system, tenant, or user.

    Resolution precedence when a consumer asks for a key: USER > TENANT >
    SYSTEM. Uniqueness is enforced across the (scope, scope_id, key) tuple
    so the same key can live at different scopes without collision.

    ``scope_id`` is an empty string for SYSTEM (never NULL) so the composite
    unique constraint behaves identically on SQLite and PostgreSQL — PG
    treats NULL as distinct in UNIQUE by default.
    """

    __tablename__ = TABLE_SETTING
    __table_args__ = (UniqueConstraint("scope", "scope_id", "key", name=UQ_SCOPE_KEY),)

    id: int | None = Field(default=None, primary_key=True)
    scope: str = Field(default=SCOPE_SYSTEM, max_length=SCOPE_MAX_LENGTH, index=True)
    scope_id: str = Field(default=SYSTEM_SCOPE_ID, max_length=SCOPE_ID_MAX_LENGTH, index=True)
    key: str = Field(max_length=KEY_MAX_LENGTH, index=True)
    value: str = Field(max_length=VALUE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
