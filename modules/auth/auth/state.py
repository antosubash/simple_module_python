"""Module-owned state attached to ``app.state.auth`` by ``AuthModule.register_settings``.

Holds the auth provider (set by one of ``users`` or ``keycloak``) and the
principal-resolver registry. Apps register additional resolvers from their
``on_startup`` hook::

    app.state.auth.principal_resolvers.append(my_pat_resolver)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from auth.contracts.resolver import PrincipalResolver

if TYPE_CHECKING:
    from auth.contracts.provider import AuthProvider


@dataclass
class AuthState:
    """Per-app auth registry. Initialized empty; provider modules populate at boot."""

    auth_provider: AuthProvider | None = None
    principal_resolvers: list[PrincipalResolver] = field(default_factory=list)


__all__ = ["AuthState"]
