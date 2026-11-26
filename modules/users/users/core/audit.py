"""How user and linked rows are named, and reached, from the audit log.

An audit entry stores ``User`` and a uuid. Turning that back into something a
reader can act on has two halves and both belong here: *where* the record
lives (the admin route) and *what it is called* (``DirectoryUser.label``).

The resolvers are deliberately batched: an audit page is 50 rows and a busy
afternoon is 50 edits to the same handful of accounts, so they take every id on
the page at once. Users take one query; role assignments take one per side.
"""

from __future__ import annotations

import uuid
from typing import Any

from simple_module_core.access.user_directory import resolve_user_labels as _labels_via
from simple_module_core.web.audit_links import AuditLink
from simple_module_db.auditing.audit import parse_uuid_pk
from sqlalchemy import select

from users.core.constants import Permissions
from users.core.directory import UsersDirectory
from users.models import OAuthAccount, Role, User, UserRole

_LABEL = "User"
_LABEL_KEY = "users.audit.user"

_DIRECTORY = UsersDirectory()


def linked_user_audit_links() -> list[AuditLink]:
    """Declare ownership even for join rows that have no individual screen."""
    return [
        AuditLink.for_model(OAuthAccount, url_template="", user_id_field="user_id"),
        AuditLink.for_model(
            UserRole,
            url_template="",
            user_id_field="user_id",
            label_resolver=resolve_user_role_labels,
            label_permission=Permissions.MANAGE,
        ),
    ]


async def resolve_user_role_labels(db: Any, ids: list[str]) -> dict[str, str]:
    """Name composite UUID keys, including assignments that have been removed."""
    pairs: dict[str, tuple[uuid.UUID, uuid.UUID]] = {}
    for raw in ids:
        parsed = parse_uuid_pk(raw)
        if parsed is None or len(parsed) != 2:
            continue
        pairs[raw] = (parsed[0], parsed[1])
    if not pairs:
        return {}

    # Read both sides directly: a revoked assignment no longer has a join row.
    user_ids = {user_id for user_id, _ in pairs.values()}
    role_ids = {role_id for _, role_id in pairs.values()}
    users = dict((await db.execute(select(User.id, User.email).where(User.id.in_(user_ids)))).all())
    roles = dict((await db.execute(select(Role.id, Role.name).where(Role.id.in_(role_ids)))).all())
    return {
        raw: f"{roles[role_id]} · {users[user_id]}"
        for raw, (user_id, role_id) in pairs.items()
        if user_id in users and role_id in roles
    }


async def resolve_user_labels(db: Any, ids: list[str]) -> dict[str, str]:
    """Map user id -> display name for every id given.

    Ids that do not parse as uuids belong to some other id space (a worker
    name, say) and ids that no longer resolve belong to deleted accounts.
    Both are simply absent from the result rather than an error: the caller
    falls back to the raw id, which is still the truthful record. The naming
    rule itself is ``DirectoryUser.label``, shared with every other screen.
    """
    return await _labels_via(_DIRECTORY, db, ids)


def build_user_audit_link(admin_url_prefix: str) -> AuditLink:
    """The registry entry for user rows, rooted at the module's admin route."""
    return AuditLink.for_model(
        User,
        url_template=f"{admin_url_prefix}{{id}}",
        label=_LABEL,
        label_key=_LABEL_KEY,
        label_resolver=resolve_user_labels,
        # A name here is the same disclosure the user list makes, so it takes
        # the same permission. Without it, a role holding `audit_log.view` and
        # nothing else could read the display name of every account that has
        # ever been edited — and the email of every account still holding an
        # unaccepted invite, since those have no `full_name` yet. The audit row
        # itself is not withheld: a reader without `users.manage` still sees
        # that a `User` was updated and which id, just not who. GH #300.
        label_permission=Permissions.MANAGE,
    )
