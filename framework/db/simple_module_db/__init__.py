"""SimpleModule DB — async SQLAlchemy/SQLModel runtime shared by every module."""

from simple_module_db.auditing.audit import AuditRecord
from simple_module_db.auditing.bulk_audit import UnauditedWriteError, record_bulk_audit
from simple_module_db.engine.callbacks import OnCommitCallback
from simple_module_db.engine.deps import get_db
from simple_module_db.engine.independent import independent_session
from simple_module_db.engine.provider import DatabaseProvider, detect_provider
from simple_module_db.engine.session import DatabaseState, RequestSession, init_db
from simple_module_db.engine.transaction import CommitBeforeResponseMiddleware, finalize_session
from simple_module_db.engine.writes import hard_delete, mark_written
from simple_module_db.models.base import create_module_base
from simple_module_db.models.extensions import UnsupportedDatabaseError, ensure_db_extensions
from simple_module_db.models.mixins import (
    AuditMixin,
    MultiTenantMixin,
    SoftDeleteMixin,
    VersionedMixin,
)
from simple_module_db.models.types import AwareDateTime, LTree, TSVector
from simple_module_db.queries.pagination import (
    Page,
    PageParams,
    clamp_page,
    paginate,
    total_pages,
)
from simple_module_db.queries.principals import principal_for
from simple_module_db.queries.search import (
    LIKE_ESCAPE_CHAR,
    like_contains_pattern,
    like_prefix_pattern,
)
from simple_module_db.schema.migration_portability import drop_enums_if_postgres
from simple_module_db.schema.migrations import (
    build_module_metadata,
    make_include_object,
    make_process_revision_directives,
    render_item,
)
from simple_module_db.scoping.scopes import ScopeFilter, ScopeIsolationError, register_scope
from simple_module_db.scoping.tenancy import (
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
    no_tenant,
    tenant_context,
)

__all__ = [
    "ALL_TENANTS_OPTION",
    "DEFAULT_TENANT_ID",
    "LIKE_ESCAPE_CHAR",
    "PLATFORM_TENANT_ID",
    "TENANT_ID_PATTERN",
    "AuditMixin",
    "AuditRecord",
    "AwareDateTime",
    "CommitBeforeResponseMiddleware",
    "DatabaseProvider",
    "DatabaseState",
    "LTree",
    "MissingTenantError",
    "MultiTenantMixin",
    "OnCommitCallback",
    "Page",
    "PageParams",
    "RequestSession",
    "ScopeFilter",
    "ScopeIsolationError",
    "SoftDeleteMixin",
    "TSVector",
    "TenantIsolationError",
    "UnauditedWriteError",
    "UnsupportedDatabaseError",
    "VersionedMixin",
    "all_tenants",
    "bind_current_tenant",
    "build_module_metadata",
    "clamp_page",
    "create_module_base",
    "current_tenant_id",
    "detect_provider",
    "drop_enums_if_postgres",
    "ensure_db_extensions",
    "finalize_session",
    "get_db",
    "hard_delete",
    "independent_session",
    "init_db",
    "is_valid_tenant_id",
    "like_contains_pattern",
    "like_prefix_pattern",
    "make_include_object",
    "make_process_revision_directives",
    "mark_written",
    "no_tenant",
    "paginate",
    "principal_for",
    "record_bulk_audit",
    "register_scope",
    "render_item",
    "tenant_context",
    "total_pages",
]
