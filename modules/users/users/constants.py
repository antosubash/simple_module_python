"""Stable identifiers used by both the seed migration and tests."""

import uuid

ADMIN_ROLE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ROLE_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")

# Role name strings
ADMIN_ROLE_NAME = "admin"
USER_ROLE_NAME = "user"

# Role descriptions
ADMIN_ROLE_DESCRIPTION = "Administrator"
USER_ROLE_DESCRIPTION = "Standard user"

# Permission identifiers
PERM_USERS_MANAGE = "users.manage"
PERM_USERS_SELF_PROFILE = "users.self.profile"

# Session keys
SESSION_USER_ID_KEY = "user_id"

# Admin list-endpoint allowed filter/sort values
ALLOWED_STATUS = frozenset({"active", "disabled"})
ALLOWED_VERIFIED = frozenset({"yes", "no"})
ALLOWED_SORT = frozenset({"email", "last_login_at", "created_at"})
ALLOWED_ORDER = frozenset({"asc", "desc"})


def sanitize_list_filters(
    status: str | None,
    verified: str | None,
    sort: str,
    order: str,
) -> tuple[str | None, str | None, str, str]:
    """Coerce unknown filter values to None/defaults."""
    return (
        status if status in ALLOWED_STATUS else None,
        verified if verified in ALLOWED_VERIFIED else None,
        sort if sort in ALLOWED_SORT else "email",
        order if order in ALLOWED_ORDER else "asc",
    )
