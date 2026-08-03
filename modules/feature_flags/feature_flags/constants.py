"""Stable identifiers for the feature_flags module."""

PERM_FEATURE_FLAGS_VIEW = "feature_flags.view"
PERM_FEATURE_FLAGS_MANAGE = "feature_flags.manage"

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

MENU_LABEL = "Feature Flags"
# Trailing slash: the browse route is registered at "/" under the view
# prefix, so linking to the bare prefix costs a 307 on every navigation.
MENU_URL = "/feature_flags/"
MENU_ICON = "flag"
MENU_ORDER = 110

PAGE_BROWSE = "FeatureFlags/Browse"

API_PREFIX = "/api/feature_flags"
VIEW_PREFIX = "/feature_flags"
QP_TENANT_ID = "tenant_id"
