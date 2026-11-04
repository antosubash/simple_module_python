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
from sqlalchemy.exc import UnboundExecutionError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import UnmappedClassError

from simple_module_db import model_registry as registry

_POLICY_KEY = "sm_engine_policy"
_engine_policy: WeakKeyDictionary[Engine, Any] = WeakKeyDictionary()
_NO_POLICY = object()  # cached for a session none of whose binds has a policy
_bound = 0  # bumped by ``set_policy``: a memoized answer older than it is stale


def set_policy(engine: Engine, policy: Any) -> None:
    """Attach ``policy`` to ``engine`` and invalidate every session's memoized answer."""
    global _bound
    _engine_policy[engine] = policy
    _bound += 1


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
    """The policy for ``session``: the strictest of the binds ``get_bind`` resolves.

    Asked through the public ``Session.get_bind`` — once without a mapper and
    once per tenant-scoped model — so per-model binds and a subclass that
    overrides ``get_bind`` keep the strict policy of the engine they route to.
    A class that is no longer mapped (or has no bind) is skipped, never raised.
    The answer (a policy, or none) is memoized on ``session.info`` for the
    session's ``bind``, the number of tenant models and the policy bindings
    made; a bind added with ``bind_mapper()`` after the first statement is not
    seen.
    """
    count = (len(registry.tenant_classes), _bound)
    cached = session.info.get(_POLICY_KEY)
    if cached is not None and cached[0] is session.bind and cached[1] == count:
        return None if cached[2] is _NO_POLICY else cached[2]
    found: dict[int, Any] = {}
    for mapper in (None, *registry.tenant_classes):
        try:
            bind = session.get_bind(mapper=mapper)
        except (UnboundExecutionError, UnmappedClassError):
            continue
        policy = policy_of(bind)
        if policy is not None:
            found.setdefault(id(policy), policy)
    policies = list(found.values())
    strict = [p for p in policies if getattr(p, "tenant_strict", False)]
    policy = (strict or policies or [None])[0]
    session.info[_POLICY_KEY] = (session.bind, count, _NO_POLICY if policy is None else policy)
    return policy


__all__ = ["policy_of", "session_policy", "set_policy"]
