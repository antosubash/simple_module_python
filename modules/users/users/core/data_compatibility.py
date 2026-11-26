"""Read-only checks for ambiguous identities and legacy bearer credentials."""

from simple_module_core.migrations.data_compatibility import DataCompatibilityIssue
from sqlalchemy import String, column, func, inspect, or_, select, table, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from users.core.constants import (
    UPGRADE_HASHED_BEARER_TOKENS,
    UPGRADE_UNIQUE_EMAILS,
    UPGRADE_UNIQUE_OAUTH_IDENTITY,
)
from users.models import RefreshToken, UserAccessToken

_SHOWN_CONFLICTS = 20
DUPLICATE_EMAILS_QUERY = (
    "SELECT id, email FROM users_user WHERE lower(email) IN "
    "(SELECT lower(email) FROM users_user GROUP BY lower(email) HAVING count(*) > 1);"
)
# A SHA-256 hex digest; tokens hashed at rest (#626) are always this long.
_DIGEST_LENGTH = 64


async def check_data_compatibility(db: AsyncSession) -> list[DataCompatibilityIssue]:
    issues = await _email_conflicts(db)
    return issues + await _oauth_conflicts(db) + await _token_compatibility(db)


async def _oauth_conflicts(db: AsyncSession) -> list[DataCompatibilityIssue]:
    connection = await db.connection()
    if not await connection.run_sync(lambda sync: inspect(sync).has_table("users_oauth_account")):
        return []
    links = table(
        "users_oauth_account", *(column(c) for c in ("id", "user_id", "oauth_name", "account_id"))
    )
    users = table("users_user", column("id"), column("email"))
    identity = (links.c.oauth_name, links.c.account_id)
    duplicates = select(*identity).group_by(*identity).having(func.count() > 1)
    rows = await db.execute(
        select(*identity, links.c.user_id, users.c.email, links.c.id)
        .select_from(links.outerjoin(users, users.c.id == links.c.user_id))
        .where(tuple_(*identity).in_(duplicates))
        .order_by(*identity, links.c.user_id, links.c.id)
    )
    conflicts: dict[tuple[str, str], list[str]] = {}
    for provider, account_id, user_id, email, link_id in rows:
        conflicts.setdefault((provider, account_id), []).append(
            f"{email!r} (user {user_id}, link {link_id})"
        )
    if not conflicts:
        return []
    return [
        DataCompatibilityIssue(
            upgrade_id=UPGRADE_UNIQUE_OAUTH_IDENTITY,
            severity="error",
            message="Duplicate OAuth identities (oauth_name, account_id):\n"
            + "\n".join(
                f"({provider!r}, {account_id!r}): " + "; ".join(owners)
                for (provider, account_id), owners in conflicts.items()
            ),
            remediation_text=(
                "Before upgrading, open each affected user's admin Edit page in the previous "
                "app version (Users → user → Linked sign-ins → Remove) and remove the extra "
                "links, keeping one link per identity. Stop old workers and retry migrations. "
                "No links or users are removed automatically."
            ),
        )
    ]


async def _email_conflicts(db: AsyncSession) -> list[DataCompatibilityIssue]:
    connection = await db.connection()
    if not await connection.run_sync(lambda sync: inspect(sync).has_table("users_user")):
        return []
    users = table("users_user", column("email"))
    email = users.c.email
    duplicates = select(func.lower(email)).group_by(func.lower(email)).having(func.count() > 1)
    conflicts = list((await db.scalars(duplicates)).all())
    if not conflicts:
        return []
    # Boot and doctor output lands in logs: name the conflicts by a masked
    # address and leave the full list to an operator's own query.
    shown = ", ".join(mask_email(value) for value in conflicts[:_SHOWN_CONFLICTS])
    more = len(conflicts) - _SHOWN_CONFLICTS
    return [
        DataCompatibilityIssue(
            upgrade_id=UPGRADE_UNIQUE_EMAILS,
            severity="error",
            message=(
                f"{len(conflicts)} email address(es) are used by more than one account "
                f"in different letter case: {shown}"
                + (f" and {more} more" if more > 0 else "")
                + ". List them with: "
                + DUPLICATE_EMAILS_QUERY
                + " Give each account a distinct email before migrating; accounts are "
                "never merged or deleted."
            ),
        )
    ]


def mask_email(value: str) -> str:
    """``alice@example.com`` -> ``a***@example.com``."""
    local, _, domain = value.partition("@")
    return f"{local[:1]}***@{domain}" if domain else f"{local[:1]}***"


async def _token_compatibility(db: AsyncSession) -> list[DataCompatibilityIssue]:
    connection = await db.connection()
    for model in (RefreshToken, UserAccessToken):
        name = model.__tablename__

        def token_type(sync, name=name):
            inspector = inspect(sync)
            if not inspector.has_table(name):
                return None
            return next(
                (c["type"] for c in inspector.get_columns(name) if c["name"] == "token"), None
            )

        kind = await connection.run_sync(token_type)
        if kind is None:
            # Not migrated yet: the migration check owns that, not this one.
            continue
        # Only a column too short for a digest is wrong; TEXT or a wider VARCHAR
        # from a hand-ported revision holds hashes just as well.
        length = getattr(kind, "length", None)
        if not isinstance(kind, String) or (length is not None and length < _DIGEST_LENGTH):
            return _incompatible()
        # One probe, not a scan into Python: boot runs this every time. Stripping
        # the hex digits with nested replace() is portable (SQLite has no regex);
        # anything left over, or the wrong length, is a pre-hashing token.
        # The whole table, not a sample: a hand-ported column change can leave
        # old plaintext rows behind new hashed ones. LIMIT 1 stops at the first.
        token = table(name, column("token")).c.token
        leftover = token
        for digit in "0123456789abcdef":
            leftover = func.replace(leftover, digit, "")
        legacy = await db.scalar(
            select(1).where(or_(func.length(token) != _DIGEST_LENGTH, leftover != "")).limit(1)
        )
        if legacy is not None:
            return _incompatible()
    return []


def _incompatible() -> list[DataCompatibilityIssue]:
    return [
        DataCompatibilityIssue(
            upgrade_id=UPGRADE_HASHED_BEARER_TOKENS,
            message="Bearer-token schema or credentials predate hashing at rest. "
            "Stop all old workers and apply the token invalidation/column upgrade; "
            "clients must sign in again.",
            severity="error",
            remediation_text=(
                "From the host's development environment, run "
                f"`uv run smpy migrations prepare {UPGRADE_HASHED_BEARER_TOKENS} "
                "--head <host-head-or-label@head>`."
            ),
        )
    ]
