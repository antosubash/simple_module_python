"""User lifecycle contracts shared without a dependency on the users module."""

import uuid
from dataclasses import dataclass

from simple_module_core.events import Event


@dataclass
class UserDeleted(Event):
    """The account is gone; owners of per-user rows must durably remove them.

    Delivery is at least once, so handlers must be idempotent.
    """

    user_id: uuid.UUID
