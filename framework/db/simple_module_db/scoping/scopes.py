"""Process-wide model scopes, registered during module import or startup."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import false, inspect
from sqlalchemy.orm import Mapper


class ScopeIsolationError(RuntimeError):
    """A custom scope has no context, or a write violates its ownership."""


@dataclass(frozen=True)
class ScopeFilter:
    """A predicate shared by ORM, Core and relationship filtering.

    ``applies_to`` is a mixin class or a callable receiving a Mapper. ``criteria``
    receives a mapped class (Core: a column collection) and the context value.
    ``None`` means missing context: fail closed, or disable this scope when
    ``fail_closed=False``. ``column`` enables scalar insert ownership checks and
    stamping; ``stamp(obj, context)`` optionally stamps new ORM objects.
    Register once before serving requests; registrations are process-wide.
    """

    name: str
    applies_to: type | Callable[[Mapper], bool]
    criteria: Callable[[Any, Any], Any]
    context: ContextVar | Callable[[], Any]
    bypass_option: str
    fail_closed: bool = True
    column: str | None = None
    stamp: Callable[[Any, Any], None] | None = None
    reads_only: bool = False
    _classes: set[type] = field(default_factory=set, init=False, repr=False, compare=False)
    _table_names: set[str] = field(default_factory=set, init=False, repr=False, compare=False)

    def value(self) -> Any:
        if isinstance(self.context, ContextVar):
            try:
                return self.context.get()
            except LookupError:
                return None
        return self.context()

    def bypassed(self, options: Mapping[str, Any]) -> bool:
        return bool(options.get(self.bypass_option))

    def requires_context(self, owner: Any) -> bool:
        return self.fail_closed

    def missing_error(self, entity: str, operation: str) -> Exception:
        return ScopeIsolationError(
            f"{operation} on '{entity}' without context for scope '{self.name}'; "
            f"use execution_options({self.bypass_option}=True) for deliberate bypass"
        )

    def missing_criteria(self, target: Any) -> Any:
        return false()

    def register_model(self, cls: type) -> None:
        mapper = inspect(cls)
        assert mapper is not None
        matches = (
            issubclass(cls, self.applies_to)
            if isinstance(self.applies_to, type)
            else self.applies_to(mapper)
        )
        if matches:
            table = cls.__table__
            if self.column is not None and self.column not in table.c:
                raise ValueError(f"Scope '{self.name}': '{table.name}' has no '{self.column}'")
            self._classes.add(cls)
            self._table_names.add(table.name)


_scopes: dict[str, ScopeFilter] = {}


def register_scope(scope: ScopeFilter) -> None:
    """Register a named scope, including models already mapped. Same instance is a no-op.

    Reusing a name with another definition raises rather than replacing a policy.
    Context callbacks are synchronous and should be cheap and side-effect free.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", scope.name) or not scope.bypass_option:
        raise ValueError("A scope needs an identifier name and a nonempty bypass_option")
    previous = _scopes.get(scope.name)
    if previous is scope:
        return
    if previous is not None:
        raise ValueError(f"Scope '{scope.name}' is already registered")
    from simple_module_db.models import model_registry

    for cls in model_registry.mapped_classes:
        scope.register_model(cls)
    _scopes[scope.name] = scope
    # Relationships may already be configured (e.g. startup registration).
    from simple_module_db.scoping._secondary_scope import scope_relationship

    for cls in model_registry.mapped_classes:
        mapper = inspect(cls)
        if mapper.configured:
            for prop in mapper.relationships:
                scope_relationship(prop)


@dataclass(frozen=True)
class ResolvedScope:
    scope: ScopeFilter
    value: Any
    required: bool = False

    @property
    def active(self) -> bool:
        return self.value is not None or self.required

    def predicate(self, target: Any) -> Any:
        return (
            self.scope.missing_criteria(target)
            if self.required
            else self.scope.criteria(target, self.value)
        )


def resolve_scopes(
    owner: Any, options: Mapping[str, Any], *, is_write: bool = False
) -> list[ResolvedScope]:
    resolved = []
    for scope in _scopes.values():
        if (is_write and scope.reads_only) or scope.bypassed(options):
            continue
        value = scope.value()
        resolved.append(
            ResolvedScope(scope, value, value is None and scope.requires_context(owner))
        )
    return resolved
