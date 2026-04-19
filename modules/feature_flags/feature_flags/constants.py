"""Stable identifiers for the feature_flags module."""

# Permission identifiers
PERM_FEATURE_FLAGS_VIEW = "feature_flags.view"
PERM_FEATURE_FLAGS_MANAGE = "feature_flags.manage"

# DB table name (SQLite lacks per-module schemas, so the prefix is load-bearing)
TABLE_OVERRIDE = "feature_flags_override"
UQ_OVERRIDE_NAME = "uq_feature_flags_override_name"

# i18n namespace — matches locale_dirs() key
LOCALE_NAMESPACE = "feature_flags"

# Menu metadata
MENU_LABEL = "Feature Flags"
MENU_URL = "/feature_flags"
MENU_ICON = "flag"
MENU_ORDER = 45

# Inertia page identifiers
PAGE_BROWSE = "FeatureFlags/Browse"
