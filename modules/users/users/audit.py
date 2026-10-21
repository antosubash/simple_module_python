"""How a user row is named, and reached, from the audit log.

An audit entry stores ``User`` and a uuid. Turning that back into something a
reader can act on has two halves and both belong here: *where* the record
lives (the admin route) and *what it is called* (``DirectoryUser.label``).

The resolver is deliberately batched: an audit page is 50 rows and a busy
afternoon is 50 edits to the same handful of accounts, so it takes every id on
the page and answers in one query.
"""

from __future__ import annotations

from typing import Any

from simple_module_core.audit_links import AuditLink
from simple_module_core.user_directory import resolve_user_labels as _labels_via

from users.constants import PERM_USERS_MANAGE
from users.directory import UsersDirectory
from users.models import User

_LABEL = "User"
_LABEL_KEY = "users.audit.user"

_DIRECTORY = UsersDirectory()


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
        label_permission=PERM_USERS_MANAGE,
    )
