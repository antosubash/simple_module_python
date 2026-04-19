"""SQLModel tables for the Settings module."""

from __future__ import annotations

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlmodel import Field

from settings.constants import (
    DESCRIPTION_MAX_LENGTH,
    KEY_MAX_LENGTH,
    MODULE_PACKAGE,
    TABLE_SETTING,
    VALUE_MAX_LENGTH,
)

Base = create_module_base(MODULE_PACKAGE)


class Setting(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """A key/value configuration entry."""

    __tablename__ = TABLE_SETTING

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(max_length=KEY_MAX_LENGTH, unique=True, index=True)
    value: str = Field(max_length=VALUE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
