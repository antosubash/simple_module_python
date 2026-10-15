"""Durable (at-least-once, cross-process) event delivery primitives.

``EventBus.publish`` is in-process and forgets an event the moment the process
dies. A *durable* subscription is delivered by a transport instead: the event is
written to an outbox in the publisher's own transaction and a worker runs the
handler later, retrying until it succeeds. The framework only defines the
contract — the subscription registry, the event (de)serialisation and the
transport protocol. ``background_tasks`` ships the transport.

Handlers are called as ``await handler(event, ctx)`` where ``ctx`` is a
:class:`DurableContext`. Delivery is at-least-once; a handler that writes only
through ``ctx.db`` gets exactly-once *database* effects, because the transport
commits that session in the same transaction that marks the delivery done.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any, Protocol, runtime_checkable

from pydantic import TypeAdapter


class DurableDeliveryUnavailable(RuntimeError):  # noqa: N818 - name fixed by the design
    """``publish_durable`` was called but no durable transport is installed.

    Durable delivery needs an outbox and a worker; the ``background_tasks``
    module installs both. Raised instead of silently degrading to in-process
    delivery, which would drop the guarantee the caller asked for.
    """


@dataclass(frozen=True)
class DurableContext:
    """What a durable handler receives next to the event.

    ``db`` is an ``AsyncSession`` the transport commits together with marking
    the delivery done — write through it and the effect lands exactly once.
    ``attempt`` is 1 on the first delivery and grows on each retry.
    """

    db: Any
    attempt: int


type DurableHandler = Callable[[Any, DurableContext], Awaitable[None]]


@runtime_checkable
class DurableTransport(Protocol):
    """Persists an event for later delivery to the named durable handlers.

    ``enqueue`` must write in *db*'s transaction, so that a rollback of the
    publisher's transaction also discards the event.
    """

    async def enqueue(self, event: Any, handler_names: Sequence[str], db: Any) -> None: ...


@dataclass(frozen=True)
class DurableSubscription:
    event_type: type
    name: str
    handler: DurableHandler


def event_key(event_type: type) -> str:
    """The stable wire name of an event type (same key ``EventBus`` uses)."""
    return f"{event_type.__module__}.{event_type.__qualname__}"


def handler_name(handler: Callable[..., Any]) -> str:
    """Default durable name: the handler's import path."""
    module = getattr(handler, "__module__", None) or "unknown"
    qualname = getattr(handler, "__qualname__", None) or repr(handler)
    return f"{module}.{qualname}"


@cache
def _adapter(event_type: type) -> TypeAdapter[Any]:
    return TypeAdapter(event_type)


def check_serializable(event_type: type) -> None:
    """Fail fast at subscribe time if *event_type* cannot travel as JSON.

    The class itself must be decorated with ``@dataclass``: a bare subclass of
    one inherits ``is_dataclass`` but silently drops its own annotated fields.
    """
    if not (isinstance(event_type, type) and "__dataclass_fields__" in vars(event_type)):
        raise TypeError(f"Durable events must be @dataclass classes; got {event_type!r}")
    try:
        adapter = _adapter(event_type)
        if not getattr(adapter, "pydantic_complete", True):
            # An annotation pydantic could not resolve (a forward reference to
            # a name not importable from the event's module).
            adapter.rebuild(raise_errors=True)
    except Exception as exc:
        raise TypeError(
            f"Event {event_key(event_type)} cannot be serialised for durable delivery: {exc}"
        ) from exc


def serialize_event(event: Any) -> dict[str, Any]:
    """Event → JSON-compatible dict. UUID, datetime, Enum, Decimal and nested
    dataclasses become their JSON forms."""
    check_serializable(type(event))
    return _adapter(type(event)).dump_python(event, mode="json")


def deserialize_event(event_type: type, payload: dict[str, Any]) -> Any:
    """JSON dict → an instance of *event_type* (inverse of :func:`serialize_event`)."""
    return _adapter(event_type).validate_python(payload)


class DurableRegistry:
    """Durable subscriptions of one ``EventBus``, keyed by (event key, name)."""

    def __init__(self) -> None:
        self._subs: dict[str, dict[str, DurableSubscription]] = {}
        self._types: dict[str, type] = {}

    def add(self, event_type: type, handler: DurableHandler, name: str | None) -> str:
        if not callable(handler):
            raise TypeError("Durable handler must be callable")
        check_serializable(event_type)
        key = event_key(event_type)
        resolved = name or handler_name(handler)
        by_name = self._subs.setdefault(key, {})
        existing = by_name.get(resolved)
        if existing is not None and existing.handler != handler:
            raise ValueError(
                f"Durable handler name {resolved!r} is already subscribed to {key}; "
                "pass a distinct name="
            )
        by_name[resolved] = DurableSubscription(event_type, resolved, handler)
        self._types[key] = event_type
        return resolved

    def handler_names(self, event_type: type) -> list[str]:
        return list(self._subs.get(event_key(event_type), {}))

    def lookup(self, key: str, name: str) -> DurableSubscription | None:
        return self._subs.get(key, {}).get(name)

    def event_type(self, key: str) -> type | None:
        return self._types.get(key)

    def __len__(self) -> int:
        return sum(len(v) for v in self._subs.values())


__all__ = [
    "DurableContext",
    "DurableDeliveryUnavailable",
    "DurableHandler",
    "DurableRegistry",
    "DurableSubscription",
    "DurableTransport",
    "deserialize_event",
    "event_key",
    "handler_name",
    "serialize_event",
]
