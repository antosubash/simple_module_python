"""SimpleModule DB - SQLAlchemy async support with per-module schema isolation."""

from simple_module_db.base import create_module_base
from simple_module_db.deps import get_db
from simple_module_db.listeners import TenantIsolationError, current_tenant_id
from simple_module_db.migrations import build_module_metadata, make_include_object
from simple_module_db.mixins import AuditMixin, MultiTenantMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.provider import DatabaseProvider, detect_provider
from simple_module_db.session import DatabaseState, init_db

__all__ = [
    "create_module_base",
    "AuditMixin",
    "SoftDeleteMixin",
    "MultiTenantMixin",
    "VersionedMixin",
    "TenantIsolationError",
    "current_tenant_id",
    "init_db",
    "DatabaseState",
    "get_db",
    "DatabaseProvider",
    "detect_provider",
    "build_module_metadata",
    "make_include_object",
]
