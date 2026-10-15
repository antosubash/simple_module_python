"""Stable identifiers for the api_tokens module."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from auth.contracts.tokens import PAT_PREFIX, SERVICE_KEY_PREFIX

MODULE_NAME: Final = "ApiTokens"
MODULE_PACKAGE: Final = "api_tokens"
LOCALE_NAMESPACE: Final = "api_tokens"

# Modules this one needs registered first: Auth owns the resolver chain,
# Users owns the accounts a personal token acts for, Settings stores
# ``max_lifetime_days``.
MODULE_AUTH: Final = "Auth"
MODULE_USERS: Final = "Users"
MODULE_SETTINGS: Final = "Settings"


class TokenKind(StrEnum):
    PERSONAL = "personal"
    SERVICE = "service"


KIND_PREFIX: Final = {TokenKind.PERSONAL: PAT_PREFIX, TokenKind.SERVICE: SERVICE_KEY_PREFIX}

# Secret: 32 random bytes in base62, left-padded to a fixed width so a
# well-formed token can be recognised without touching the database.
SECRET_BYTES: Final = 32
SECRET_LENGTH: Final = 43  # ceil(256 / log2(62))
DISPLAY_PREFIX_LENGTH: Final = 8

# Prefix is load-bearing on SQLite, which has no per-module schemas.
TABLE_TOKEN: Final = "api_tokens_token"
IX_TOKEN_HASH: Final = "ix_api_tokens_token_hash_tenant"
NAME_MAX_LENGTH: Final = 100
MAX_SCOPES: Final = 200

# How stale ``last_used_at`` may get before a request rewrites it. Bounds
# the write load to one conditional UPDATE per token per window.
LAST_USED_WRITE_INTERVAL_SECONDS: Final = 300

PERM_GROUP: Final = "API tokens"
PERM_USE: Final = "api_tokens.use"
PERM_MANAGE: Final = "api_tokens.manage"
USER_ROLE: Final = "user"

# Roles a service key may never hold: ``admin`` would be the wildcard on a
# credential with no person behind it.
FORBIDDEN_SERVICE_ROLES: Final = frozenset({"admin"})

API_PREFIX: Final = "/api/api_tokens"
VIEW_PREFIX: Final = "/api-tokens"
ADMIN_VIEW_PREFIX: Final = "/admin/api-tokens"
# Trailing slash: both index routes are registered at "/" under their prefix.
USER_URL: Final = f"{VIEW_PREFIX}/"
ADMIN_URL: Final = f"{ADMIN_VIEW_PREFIX}/"

PAGE_INDEX: Final = "ApiTokens/Index"
PAGE_ADMIN: Final = "ApiTokens/Admin"

MENU_LABEL: Final = "API tokens"
MENU_LABEL_KEY: Final = "api_tokens.nav.api_tokens"
MENU_USER_ORDER: Final = 980
MENU_ADMIN_ORDER: Final = 130
MENU_ICON: Final = "key"

AUDIT_LINK_LABEL: Final = "API token"
AUDIT_LINK_LABEL_KEY: Final = "api_tokens.audit.token"
QP_TOKEN: Final = "token"

# Expiry presets offered by the pages, in days; the server accepts any whole
# number of days up to ``max_lifetime_days``.
EXPIRY_PRESETS_DAYS: Final = (7, 30, 90, 365)
