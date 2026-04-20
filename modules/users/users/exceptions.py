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
