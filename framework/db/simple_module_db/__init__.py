"""SimpleModule DB — async SQLAlchemy/SQLModel runtime shared by every module."""

from simple_module_db.audit import AuditRecord
from simple_module_db.base import create_module_base
from simple_module_db.callbacks import OnCommitCallback
from simple_module_db.deps import get_db
from simple_module_db.migration_portability import drop_enums_if_postgres
from simple_module_db.migrations import (
    build_module_metadata,
    make_include_object,
    make_process_revision_directives,
    render_item,
)
from simple_module_db.mixins import AuditMixin, MultiTenantMixin, SoftDeleteMixin, VersionedMixin
from simple_module_db.provider import DatabaseProvider, detect_provider
from simple_module_db.search import LIKE_ESCAPE_CHAR, like_contains_pattern, like_prefix_pattern
from simple_module_db.session import DatabaseState, RequestSession, init_db
from simple_module_db.tenancy import (
    ALL_TENANTS_OPTION,
    DEFAULT_TENANT_ID,
    PLATFORM_TENANT_ID,
    TENANT_ID_PATTERN,
    MissingTenantError,
    TenantIsolationError,
    all_tenants,
    bind_current_tenant,
    current_tenant_id,
    is_valid_tenant_id,
    tenant_context,
)
from simple_module_db.transaction import CommitBeforeResponseMiddleware, finalize_session
from simple_module_db.writes import hard_delete, mark_written

__all__ = [
    "ALL_TENANTS_OPTION",
    "DEFAULT_TENANT_ID",
    "LIKE_ESCAPE_CHAR",
    "PLATFORM_TENANT_ID",
    "TENANT_ID_PATTERN",
    "AuditMixin",
    "AuditRecord",
    "CommitBeforeResponseMiddleware",
    "DatabaseProvider",
    "DatabaseState",
    "MissingTenantError",
    "MultiTenantMixin",
    "OnCommitCallback",
    "RequestSession",
    "SoftDeleteMixin",
    "TenantIsolationError",
    "VersionedMixin",
    "all_tenants",
    "bind_current_tenant",
    "build_module_metadata",
    "create_module_base",
    "current_tenant_id",
    "detect_provider",
    "drop_enums_if_postgres",
    "finalize_session",
    "get_db",
    "hard_delete",
    "init_db",
    "is_valid_tenant_id",
    "like_contains_pattern",
    "like_prefix_pattern",
    "make_include_object",
    "make_process_revision_directives",
    "mark_written",
    "render_item",
    "tenant_context",
]
