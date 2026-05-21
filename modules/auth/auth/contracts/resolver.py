"""Principal-resolver extension point — apps register additional auth sources here.

A ``PrincipalResolver`` is an async callable that inspects an incoming
``Request`` and returns a :class:`~auth.contracts.schemas.UserContext` if it
can authenticate the caller, or ``None`` to fall through to the next resolver
in the chain.

The chain is consulted by ``users.middleware.AuthMiddleware`` *after* the
session-cookie path has been tried, in registration order, and the first
non-``None`` return wins.

Invariants every resolver MUST satisfy:

* **Async.** Resolvers are awaited.
* **Cheap fast-path bail.** Resolvers run on every request; return ``None``
  immediately when the credential type isn't present (e.g., no ``Authorization``
  header, no matching scheme).
* **Self-checks active/disabled state.** The middleware does NOT re-validate
  the user after the resolver returns — return ``None`` for disabled,
  unverified, or otherwise blocked users.
* **Never raise on bad credentials.** Return ``None`` and let the chain
  continue. The middleware wraps each resolver in ``try/except`` for
  defense in depth, but resolver authors should not rely on it.
* **Request-scoped — no session writes.** A PAT call must not silently
  elevate to a long-lived session cookie. If the resolver needs to mint a
  session, that's an entirely separate code path (the standard login flow).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request

from auth.contracts.schemas import UserContext

PrincipalResolver = Callable[[Request], Awaitable[UserContext | None]]
"""Async callable: ``(Request) -> UserContext | None``. See module docstring
for the invariants resolver authors must uphold."""

__all__ = ["PrincipalResolver"]
