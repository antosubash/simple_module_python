"""SQLModel tables for the {{MODULE_NAME}} module."""

from __future__ import annotations

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlmodel import Field

from {{PACKAGE_NAME}}.constants import (
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
    TABLE_{{SINGULAR_UPPER}},
)

Base = create_module_base("{{PACKAGE_NAME}}")


class {{SINGULAR_CLASS}}(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """A {{SINGULAR}} entity."""

    __tablename__ = TABLE_{{SINGULAR_UPPER}}

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    is_active: bool = Field(default=True)
