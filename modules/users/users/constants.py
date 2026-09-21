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
# Revocation stamp copied out of ``User.session_version`` at login. A session
# whose stamp has fallen behind the account's was minted before the owner
# pressed "Sign out everywhere", so the auth provider refuses it. Absent means
# 0, which is what every session predating the column carries.
SESSION_VERSION_KEY = "session_version"
# Stamped by the demo sign-in endpoint so ``DemoReadOnlyMiddleware`` can
# recognise a shared demo session without a database read. Lives here rather
# than in ``users.demo`` because ``manager``/``provider`` have to clear it on
# every *other* sign-in and on every session teardown, and neither of those
# should have to import the seeding module to do it. Re-exported from
# ``users.demo``, which is where the feature's own code reads it from.
SESSION_DEMO_KEY = "is_demo"

# request.state flag set by the OAuth callback before find-or-create so the
# manager's on_after_register hook can mark *newly provisioned* OAuth users as
# external (null password). on_after_register fires only for new users, so the
# flag is ignored when an OAuth login merely links to an existing account.
OAUTH_REGISTRATION_REQUEST_FLAG = "users_oauth_registration"

# Admin list-endpoint allowed filter/sort values
# "active" here means active *and* verified: the table shows unverified and
# invited as their own states, so folding them back into "active" would make
# the filter disagree with the pill beside every row it returned.
ALLOWED_STATUS = frozenset({"active", "unverified", "invited", "disabled"})
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
