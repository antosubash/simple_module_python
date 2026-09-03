"""Domain-level exceptions raised by the users module.

Kept internal to the module — callers in the endpoints layer translate these
into HTTP responses. Not re-exported via ``contracts/`` because no other
module catches them today. Promote to contracts if that changes.
"""

from __future__ import annotations

import uuid


class UserNotFoundError(Exception):
    """Raised when a user lookup by id/email returns nothing."""

    def __init__(self, user_id: uuid.UUID) -> None:
        super().__init__(f"User {user_id} not found")
        self.user_id = user_id


class EmailAlreadyExistsError(Exception):
    """Raised when updating a user to an email already owned by another user."""

    def __init__(self, email: str) -> None:
        super().__init__(f"Email {email} already in use")
        self.email = email


class ExternalUserNoPasswordError(Exception):
    """Raised when a password-credential action targets an external (SSO) user.

    External users have no local password, so password reset / set has no
    meaning for them. Endpoints translate this into a 4xx.
    """

    def __init__(self, user_id: uuid.UUID) -> None:
        super().__init__(f"User {user_id} is external (SSO) and has no password")
        self.user_id = user_id


class NotPendingInviteError(Exception):
    """Raised when resending an invite to a row that is not awaiting one.

    Resend is only offered on rows in the ``invited`` state, so reaching this
    means a stale tab or a hand-written request. Refusing matters for three
    different reasons, and ``reason`` keeps them apart in the message the admin
    sees: an accepted account has nothing left to accept, a self-signup was
    never invited by anyone (re-inviting would rewrite its history), and a
    disabled account must not be handed a live token that lets it back in.

    Crucially none of these flip the account's state to make the request work.
    """

    def __init__(self, user_id: uuid.UUID, reason: str) -> None:
        super().__init__(f"User {user_id} has no pending invite: {reason}")
        self.user_id = user_id
        self.reason = reason
