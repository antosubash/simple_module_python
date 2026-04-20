"""Module-scoped state container for the users module.

Stored as ``app.state.users`` by :meth:`UsersModule.register_settings` (for
fields available at that phase) and populated the rest of the way during
:meth:`UsersModule.on_startup` (for fields that depend on the DB or other
framework services).

Not frozen — ``on_startup`` needs to set fields that aren't available at
``register_settings`` time. Convention: set once during boot, treat as
read-only after.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from users.mailer import Mailer
    from users.rate_limit import LoginRateLimiter, ThroughputLimiter
    from users.roles_cache import RoleSummary
    from users.settings import UsersSettings


@dataclass
class UsersState:
    """Users-module singletons. Single slot at ``app.state.users``."""

    settings: UsersSettings
    mailer: Mailer | None = None
    rate_limiter: LoginRateLimiter | None = None
    auth_throughput_limiter: ThroughputLimiter | None = None
    roles_cache: list[RoleSummary] = field(default_factory=list)
