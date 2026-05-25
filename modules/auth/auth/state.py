"""Module-owned state attached to ``app.state.auth`` by ``AuthModule.register_settings``.

Holds the principal-resolver registry (see
``auth.contracts.resolver.PrincipalResolver``). Apps register additional
resolvers from their ``on_startup`` hook::

    app.state.auth.principal_resolvers.append(my_pat_resolver)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from auth.contracts.resolver import PrincipalResolver


@dataclass
class AuthState:
    """Per-app auth registry. Initialized empty; modules append resolvers."""

    principal_resolvers: list[PrincipalResolver] = field(default_factory=list)


__all__ = ["AuthState"]
