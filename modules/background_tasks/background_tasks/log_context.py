"""Contextvars-based log context for Celery tasks.

Workers run outside the HTTP request lifecycle, so the hosting layer's
``correlation_id`` ContextVar doesn't reach them. This module gives task
code the equivalent affordance: ``task_id`` / ``task_name`` bound from
Celery signals plus arbitrary domain identifiers via
:func:`bind_task_context`. See ``modules/background_tasks/README.md``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from types import MappingProxyType
from typing import Any

# Read-only so a future caller can't mutate the shared default in place.
_EMPTY: Mapping[str, Any] = MappingProxyType({})

current_log_context: ContextVar[Mapping[str, Any]] = ContextVar(
    "current_log_context", default=_EMPTY
)

# Stdlib LogRecord populates these attrs by default. Binding a key with
# the same name would be silently shadowed by the LogRecord attr (or
# rejected by stdlib's own makeRecord guard), so we reject at bind time
# instead of at log time.
_RESERVED_RECORD_KEYS: frozenset[str] = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
}

# Pairs ``task_prerun`` → ``task_postrun`` across signal calls. Keyed by
# Celery task UUID so threaded / gevent pools — which can interleave
# prerun/postrun pairs within one process — stay isolated.
_signal_tokens: dict[str, Token[Mapping[str, Any]]] = {}

_log = logging.getLogger(__name__)


def get_log_context() -> dict[str, Any]:
    """Return a snapshot of every currently-bound key."""
    return dict(current_log_context.get())


@contextmanager
def bind_task_context(**identifiers: Any) -> Iterator[None]:
    """Layer ``identifiers`` onto the current task's log context.

    Nests cleanly. Raises ``ValueError`` if any key collides with a
    stdlib :class:`LogRecord` attribute (``name``, ``module``, ...) —
    those would be silently shadowed downstream.
    """
    collisions = identifiers.keys() & _RESERVED_RECORD_KEYS
    if collisions:
        raise ValueError(
            f"Cannot bind log-context keys that collide with LogRecord "
            f"attributes: {sorted(collisions)}"
        )
    merged = {**current_log_context.get(), **identifiers}
    token = current_log_context.set(merged)
    try:
        yield
    finally:
        current_log_context.reset(token)


class LogContextFilter(logging.Filter):
    """Copy bound log-context keys onto each :class:`LogRecord`.

    Attached via :func:`install_log_filter`; downstream formatters read
    ``record.task_id`` etc. when emitting the line.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = current_log_context.get()
        if not ctx:
            return True
        record_dict = record.__dict__
        for key, value in ctx.items():
            # An explicit ``extra={key: ...}`` on the logger call wins.
            record_dict.setdefault(key, value)
        return True


def install_log_filter(logger: logging.Logger | None = None) -> LogContextFilter:
    """Attach a :class:`LogContextFilter` to ``logger`` (root if omitted). Idempotent."""
    target = logger if logger is not None else logging.getLogger()
    for existing in target.filters:
        if isinstance(existing, LogContextFilter):
            return existing
    log_filter = LogContextFilter()
    target.addFilter(log_filter)
    return log_filter


def signal_task_started(*, task_id: str | None, task_name: str | None) -> None:
    """Bind ``task_id`` / ``task_name`` for a Celery task's duration.

    Paired with :func:`signal_task_finished` via the postrun signal.
    """
    if not task_id:
        return
    merged = {**current_log_context.get(), "task_id": task_id, "task_name": task_name}
    _signal_tokens[task_id] = current_log_context.set(merged)


def signal_task_finished(*, task_id: str | None) -> None:
    """Reset the binding from :func:`signal_task_started`."""
    if not task_id:
        return
    token = _signal_tokens.pop(task_id, None)
    if token is None:
        return
    try:
        current_log_context.reset(token)
    except ValueError:
        # Token belongs to a different context — possible under exotic
        # eventlet patching. The var falls back when the task's context
        # exits, so the leak is bounded.
        _log.debug("Log-context reset skipped for task_id=%s", task_id)
