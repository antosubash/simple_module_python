"""Stable identifiers for the feature_flags module."""

# Permission identifiers
PERM_FEATURE_FLAGS_VIEW = "feature_flags.view"
PERM_FEATURE_FLAGS_MANAGE = "feature_flags.manage"

# DB table name (SQLite lacks per-module schemas, so the prefix is load-bearing)
TABLE_OVERRIDE = "feature_flags_override"
UQ_OVERRIDE_SCOPE_NAME = "uq_feature_flags_override_scope_scope_id_name"

# Override scopes — system applies globally, tenant applies only when a request
# carries that tenant_id. Resolution: tenant > system > definition default.
SCOPE_SYSTEM = "system"
SCOPE_TENANT = "tenant"
ALL_SCOPES = (SCOPE_SYSTEM, SCOPE_TENANT)
# Empty string (not NULL) so the composite unique works on PG, where multiple
# NULLs would collide-free and let two "system" rows for the same flag exist.
SYSTEM_SCOPE_ID = ""

SCOPE_MAX_LENGTH = 10
SCOPE_ID_MAX_LENGTH = 64

# i18n namespace — matches locale_dirs() key
LOCALE_NAMESPACE = "feature_flags"

# Menu metadata
MENU_LABEL = "Feature Flags"
MENU_URL = "/feature_flags"
MENU_ICON = "flag"
MENU_ORDER = 45

# Inertia page identifiers
PAGE_BROWSE = "FeatureFlags/Browse"

# Routing
API_PREFIX = "/api/feature_flags"
VIEW_PREFIX = "/feature_flags"
QP_TENANT_ID = "tenant_id"
