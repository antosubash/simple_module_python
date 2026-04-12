"""SimpleModule DB - SQLAlchemy async support with per-module schema isolation."""

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin, MultiTenantMixin, VersionedMixin
from simple_module_db.session import init_db, get_engine, get_session_factory
from simple_module_db.deps import get_db
from simple_module_db.provider import DatabaseProvider, detect_provider

__all__ = [
    "create_module_base",
    "AuditMixin",
    "SoftDeleteMixin",
    "MultiTenantMixin",
    "VersionedMixin",
    "init_db",
    "get_engine",
    "get_session_factory",
    "get_db",
    "DatabaseProvider",
    "detect_provider",
]
