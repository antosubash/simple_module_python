"""Centralized constants for the Settings module.

Keeps module-level strings (route prefixes, permission ids, table names,
menu metadata, error messages, field limits, env prefix, i18n namespace,
scope identifiers) in one place so nothing is duplicated in Python or
inline-literal'd at call sites.
"""

from __future__ import annotations

from typing import Final

# ── Module identity ──────────────────────────────────────────────────
MODULE_NAME: Final = "Settings"
MODULE_PACKAGE: Final = "settings"
ENV_PREFIX: Final = "SM_SETTINGS_"
LOCALE_NAMESPACE: Final = MODULE_PACKAGE

# ── Scopes ───────────────────────────────────────────────────────────
# Precedence high → low when resolving a key: USER > TENANT > SYSTEM.
SCOPE_SYSTEM: Final = "system"
SCOPE_TENANT: Final = "tenant"
SCOPE_USER: Final = "user"
ALL_SCOPES: Final = (SCOPE_SYSTEM, SCOPE_TENANT, SCOPE_USER)
# scope_id is empty for SYSTEM; empty string (not NULL) so composite unique
# works uniformly on SQLite and PostgreSQL (NULL breaks uniqueness on PG).
SYSTEM_SCOPE_ID: Final = ""

# ── Value types ──────────────────────────────────────────────────────
# Values are always stored as strings; ``value_type`` tells consumers how
# to interpret the bytes and lets the UI pick the right input control.
VALUE_TYPE_STRING: Final = "string"
VALUE_TYPE_BOOL: Final = "bool"
VALUE_TYPE_INT: Final = "int"
VALUE_TYPE_FLOAT: Final = "float"
VALUE_TYPE_JSON: Final = "json"
ALL_VALUE_TYPES: Final = (
    VALUE_TYPE_STRING,
    VALUE_TYPE_BOOL,
    VALUE_TYPE_INT,
    VALUE_TYPE_FLOAT,
    VALUE_TYPE_JSON,
)

# ── Routing ──────────────────────────────────────────────────────────
API_PREFIX: Final = "/api/settings"
VIEW_PREFIX: Final = "/settings"
VIEW_CREATE_PATH: Final = "/create"
VIEW_EDIT_PATH: Final = "/{setting_id}/edit"
VIEW_MODULES_PATH: Final = "/modules"
API_BY_ID_PATH: Final = "/{setting_id}"
API_BY_KEY_PATH: Final = "/by-key/{key}"
API_RESOLVE_PATH: Final = "/resolve/{key}"
API_SYSTEM_PATH: Final = "/system/{key}"
API_TENANT_PATH: Final = "/tenant/{scope_id}/{key}"
API_USER_PATH: Final = "/user/{scope_id}/{key}"

# ── Menu ─────────────────────────────────────────────────────────────
MENU_LABEL: Final = MODULE_NAME
MENU_URL: Final = VIEW_PREFIX
MENU_ICON: Final = "settings"
MENU_ORDER: Final = 200

# ── Permissions ──────────────────────────────────────────────────────
PERM_GROUP: Final = MODULE_NAME
PERM_VIEW: Final = "settings.view"
PERM_CREATE: Final = "settings.create"
PERM_EDIT: Final = "settings.edit"
PERM_DELETE: Final = "settings.delete"
ALL_PERMISSIONS: Final = (PERM_VIEW, PERM_CREATE, PERM_EDIT, PERM_DELETE)

# ── Database ─────────────────────────────────────────────────────────
DB_SCHEMA: Final = MODULE_PACKAGE
TABLE_SETTING: Final = "settings_setting"
UQ_SCOPE_KEY: Final = "uq_settings_setting_scope_scope_id_key"

# ── Field limits ─────────────────────────────────────────────────────
KEY_MAX_LENGTH: Final = 200
VALUE_MAX_LENGTH: Final = 4000
DESCRIPTION_MAX_LENGTH: Final = 2000
SCOPE_MAX_LENGTH: Final = 10
SCOPE_ID_MAX_LENGTH: Final = 255
VALUE_TYPE_MAX_LENGTH: Final = 10

# ── Inertia page component names ─────────────────────────────────────
PAGE_BROWSE: Final = f"{MODULE_NAME}/Browse"
PAGE_CREATE: Final = f"{MODULE_NAME}/Create"
PAGE_EDIT: Final = f"{MODULE_NAME}/Edit"
PAGE_MODULES_EDIT: Final = f"{MODULE_NAME}/ModulesEdit"

# ── Inertia prop keys ────────────────────────────────────────────────
PROP_SETTINGS: Final = "settings"
PROP_SETTING: Final = "setting"
PROP_MODULES: Final = "modules"
PROP_ERROR: Final = "error"

# ── User-facing error messages ───────────────────────────────────────
ERR_SETTING_NOT_FOUND: Final = "Setting not found"
ERR_KEY_ALREADY_EXISTS: Final = "Setting key already exists"
ERR_SYSTEM_SCOPE_NO_ID: Final = "system scope must not have a scope_id"
ERR_SCOPED_REQUIRES_ID: Final = "tenant/user scope requires a scope_id"
ERR_UNKNOWN_SCOPE: Final = "unknown scope"
ERR_VALUE_MISMATCH: Final = "value does not parse as declared value_type"

# ── HTTP ─────────────────────────────────────────────────────────────
STATUS_CREATED: Final = 201
STATUS_NO_CONTENT: Final = 204
STATUS_NOT_FOUND: Final = 404
STATUS_CONFLICT: Final = 409

# ── Query parameter names ────────────────────────────────────────────
QP_USER_ID: Final = "user_id"
QP_TENANT_ID: Final = "tenant_id"
QP_SCOPE: Final = "scope"
QP_SCOPE_ID: Final = "scope_id"
