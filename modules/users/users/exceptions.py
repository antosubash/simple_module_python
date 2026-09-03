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


class AlreadyVerifiedError(Exception):
    """Raised when re-inviting an account that has already been accepted.

    Not an error the admin caused so much as one the screen should have
    prevented: Resend is only offered on pending rows. Refusing anyway keeps a
    stale tab from minting a live invite token for a working account.
    """

    def __init__(self, user_id: uuid.UUID) -> None:
        super().__init__(f"User {user_id} is already verified")
        self.user_id = user_id
