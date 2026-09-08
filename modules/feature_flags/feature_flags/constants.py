"""Stable identifiers for the feature_flags module."""

PERM_FEATURE_FLAGS_VIEW = "feature_flags.view"
PERM_FEATURE_FLAGS_MANAGE = "feature_flags.manage"
# Shown as a heading in the role editor, so it follows the same sentence case
# as the menu label and the page title rather than reading "Feature Flags"
# beside them.
PERM_GROUP = "Feature flags"

# Prefix is load-bearing on SQLite, which has no per-module schemas.
TABLE_OVERRIDE = "feature_flags_override"
UQ_OVERRIDE_SCOPE_NAME = "uq_feature_flags_override_scope_scope_id_name"

SCOPE_SYSTEM = "system"
SCOPE_TENANT = "tenant"
ALL_SCOPES = (SCOPE_SYSTEM, SCOPE_TENANT)
# Empty string, not NULL: PG treats NULLs as distinct in unique indexes,
# which would let two "system" rows for the same flag coexist.
SYSTEM_SCOPE_ID = ""

SCOPE_MAX_LENGTH = 10
SCOPE_ID_MAX_LENGTH = 64

LOCALE_NAMESPACE = "feature_flags"

MENU_LABEL = "Feature flags"
# Trailing slash: the browse route is registered at "/" under the view
# prefix, so linking to the bare prefix costs a 307 on every navigation.
MENU_URL = "/admin/feature-flags/"
MENU_ICON = "flag"
MENU_ORDER = 110

PAGE_BROWSE = "FeatureFlags/Browse"

API_PREFIX = "/api/feature_flags"
VIEW_PREFIX = "/admin/feature-flags"
QP_TENANT_ID = "tenant_id"
# Audit rows carry an override's primary key and nothing else. There is no
# per-override page to land on, so the link opens the flags screen and names
# the row it came from; an AuditLink without an "{id}" slot is rejected at
# boot because every row would otherwise resolve to the same URL.
QP_OVERRIDE = "override"
AUDIT_LINK_LABEL = "Feature flag override"
AUDIT_LINK_LABEL_KEY = "feature_flags.audit.override"

# Module name and browse URL of the audit log, used to decide whether the
# "View change history" link has anywhere to go and where. Not a dependency:
# flags work perfectly well without an audit log installed.
AUDIT_LOG_MODULE = "AuditLog"
AUDIT_LOG_VIEW_URL = "/admin/audit-log/"
