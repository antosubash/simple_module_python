"""Per-engine tenancy policy, resolved through derived engines and session binds.

Keyed by engine rather than held in a module global so two ``DatabaseState``s
in one process (tests, a CLI next to an app) cannot switch each other's
strict mode off. ``engine.execution_options(...)`` returns an ``OptionEngine``
that proxies the engine it came from, and a session may be bound per model or
table (``binds={...}``) instead of to one engine: both resolve to the policy
of the base engine.
"""

from __future__ import annotations

from typing import Any
from weakref import WeakKeyDictionary

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

_engine_policy: WeakKeyDictionary[Engine, Any] = WeakKeyDictionary()


def policy_of(bind: Any) -> Any:
    """The policy of ``bind`` (an engine, a derived engine or a connection), or ``None``."""
    if isinstance(bind, Connection):
        bind = bind.engine
    while isinstance(bind, Engine):
        found = _engine_policy.get(bind)
        if found is not None:
            return found
        bind = getattr(bind, "_proxied", None)  # ``OptionEngine`` -> its base engine
    return None


def session_policy(session: Session) -> Any:
    """The policy for ``session``: its bind's, or the strictest of its per-model binds'."""
    if session.bind is not None:
        return policy_of(session.bind)
    binds = getattr(session, "_Session__binds", None) or {}
    unique = {id(bind): bind for bind in binds.values()}.values()
    found = [p for p in map(policy_of, unique) if p is not None]
    strict = [p for p in found if getattr(p, "tenant_strict", False)]
    return (strict or found or [None])[0]


__all__ = ["policy_of", "session_policy"]
