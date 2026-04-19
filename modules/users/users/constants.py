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
