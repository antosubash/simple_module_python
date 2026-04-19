"""Centralized constants for the Settings module.

Keeps module-level strings (route prefixes, permission ids, table names,
menu metadata, error messages, field limits, env prefix, i18n namespace)
in one place so nothing is duplicated in Python or inline-literal'd at call
sites.
"""

from __future__ import annotations

from typing import Final

# ── Module identity ──────────────────────────────────────────────────
MODULE_NAME: Final = "Settings"
MODULE_PACKAGE: Final = "settings"
ENV_PREFIX: Final = "SM_SETTINGS_"
LOCALE_NAMESPACE: Final = MODULE_PACKAGE

# ── Routing ──────────────────────────────────────────────────────────
API_PREFIX: Final = "/api/settings"
VIEW_PREFIX: Final = "/settings"
VIEW_CREATE_PATH: Final = "/create"
VIEW_EDIT_PATH: Final = "/{setting_id}/edit"
API_BY_ID_PATH: Final = "/{setting_id}"
API_BY_KEY_PATH: Final = "/by-key/{key}"

# ── Menu ─────────────────────────────────────────────────────────────
MENU_LABEL: Final = MODULE_NAME
MENU_URL: Final = VIEW_PREFIX
MENU_ICON: Final = "settings"
MENU_ORDER: Final = 30

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

# ── Field limits ─────────────────────────────────────────────────────
KEY_MAX_LENGTH: Final = 200
VALUE_MAX_LENGTH: Final = 4000
DESCRIPTION_MAX_LENGTH: Final = 2000

# ── Inertia page component names ─────────────────────────────────────
PAGE_BROWSE: Final = f"{MODULE_NAME}/Browse"
PAGE_CREATE: Final = f"{MODULE_NAME}/Create"
PAGE_EDIT: Final = f"{MODULE_NAME}/Edit"

# ── Inertia prop keys ────────────────────────────────────────────────
PROP_SETTINGS: Final = "settings"
PROP_SETTING: Final = "setting"
PROP_ERROR: Final = "error"

# ── User-facing error messages ───────────────────────────────────────
ERR_SETTING_NOT_FOUND: Final = "Setting not found"
ERR_KEY_ALREADY_EXISTS: Final = "Setting key already exists"

# ── HTTP ─────────────────────────────────────────────────────────────
STATUS_CREATED: Final = 201
STATUS_NO_CONTENT: Final = 204
STATUS_NOT_FOUND: Final = 404
STATUS_CONFLICT: Final = 409
