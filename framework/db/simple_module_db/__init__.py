"""SimpleModule DB — async SQLAlchemy/SQLModel runtime shared by every module."""

from simple_module_db.audit import AuditRecord
from simple_module_db.base import create_module_base
from simple_module_db.deps import get_db
from simple_module_db.listeners import TenantIsolationError, current_tenant_id
from simple_module_db.migrations import (
    build_module_metadata,
    make_include_object,
    make_process_revision_directives,
    render_item,
)
from simple_module_db.mixins import AuditMixin, MultiTenantMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.provider import DatabaseProvider, detect_provider
from simple_module_db.search import LIKE_ESCAPE_CHAR, like_contains_pattern
from simple_module_db.session import DatabaseState, init_db

__all__ = [
    "LIKE_ESCAPE_CHAR",
    "AuditMixin",
    "AuditRecord",
    "DatabaseProvider",
    "DatabaseState",
    "MultiTenantMixin",
    "SoftDeleteMixin",
    "TenantIsolationError",
    "VersionedMixin",
    "build_module_metadata",
    "create_module_base",
    "current_tenant_id",
    "detect_provider",
    "get_db",
    "init_db",
    "like_contains_pattern",
    "make_include_object",
    "make_process_revision_directives",
    "render_item",
]
