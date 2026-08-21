"""Centralized constants for the Audit Log module."""

from __future__ import annotations

from typing import Final

MODULE_NAME: Final = "AuditLog"
MODULE_PACKAGE: Final = "audit_log"
LOCALE_NAMESPACE: Final = MODULE_PACKAGE

API_PREFIX: Final = "/api/audit_log"
VIEW_PREFIX: Final = "/admin/audit-log"

MENU_LABEL: Final = "Audit Log"
# Trailing slash: the browse route is registered at "/" under VIEW_PREFIX, so
# linking to the bare prefix costs a 307 round trip on every navigation.
MENU_URL: Final = f"{VIEW_PREFIX}/"
MENU_ICON: Final = "scroll-text"
MENU_ORDER: Final = 210

PERM_GROUP: Final = MODULE_NAME
PERM_VIEW: Final = "audit_log.view"
ALL_PERMISSIONS: Final = (PERM_VIEW,)

TABLE_AUDIT_ENTRY: Final = "audit_log_audit_entry"

ACTION_CREATED: Final = "created"
ACTION_UPDATED: Final = "updated"
ACTION_DELETED: Final = "deleted"
ACTION_SOFT_DELETED: Final = "soft_deleted"
ALL_ACTIONS: Final = (ACTION_CREATED, ACTION_UPDATED, ACTION_DELETED, ACTION_SOFT_DELETED)

ENTITY_TYPE_MAX_LENGTH: Final = 255
ENTITY_ID_MAX_LENGTH: Final = 255
ACTION_MAX_LENGTH: Final = 20
USER_ID_MAX_LENGTH: Final = 255
CORRELATION_ID_MAX_LENGTH: Final = 255

DEFAULT_PAGE_SIZE: Final = 50
MAX_PAGE_SIZE: Final = 200

PAGE_BROWSE: Final = f"{MODULE_NAME}/Browse"

STATUS_OK: Final = 200
