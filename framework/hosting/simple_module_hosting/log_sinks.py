"""Pluggable retained-log sinks (GH #537).

A :class:`LogSink` receives batches of already-redacted records. The
:class:`QueueSinkHandler` sits on a logger (normally the root) and moves
records to the sink on a background thread, so logging never waits on a
database or a network call.

Guarantees, in order of importance:

* **Never blocks.** The queue is bounded; when it is full the record is dropped
  and counted (:attr:`QueueSinkHandler.dropped`). A slow or dead sink costs log
  lines, never request latency.
* **Secrets are masked before queueing.** :func:`redact` runs on a copy of the
  record in the emitting thread, so neither the queue nor any sink ever holds
  an ``Authorization`` header, cookie, password, token or ``secret=`` value.
* **No feedback loop.** Records from this module's own logger and from
  ``sqlalchemy.*`` (what a database sink itself triggers) are skipped.
"""

from __future__ import annotations

import logging
import logging.handlers
import queue
import re
import threading
import time
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from simple_module_core.correlation import correlation_id

logger = logging.getLogger(__name__)

DEFAULT_QUEUE_CAPACITY = 10_000
DEFAULT_BATCH_SIZE = 200
DEFAULT_FLUSH_INTERVAL_SECONDS = 1.0
STOP_TIMEOUT_SECONDS = 5.0
REDACTED = "***"
# Logger names whose records are never forwarded: our own, and the SQL layer a
# database sink writes through.
SKIPPED_LOGGER_PREFIXES: tuple[str, ...] = (__name__, "sqlalchemy")

_STOP = object()

_HEADER_RE = re.compile(
    r"""(?ix)\b(proxy-authorization|authorization|set-cookie|cookie)(["']?\s*[:=]\s*["']?)[^\r\n"']*"""
)
_SECRET_RE = re.compile(
    r"""(?ix)([\w-]*(?:password|passwd|token|secret|api[_-]?key)[\w-]*["']?\s*[:=]\s*["']?)"""
    r"""[^\s"',;&}\])]+"""
)
_URL_CRED_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/@\s:]*):([^/@\s]*)@")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[\w.~+/=-]+")
_SENSITIVE_KEY_RE = re.compile(r"(?i)password|passwd|token|secret|api[_-]?key|authorization|cookie")
_STANDARD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


@runtime_checkable
class LogSink(Protocol):
    """Where batches of log records end up."""

    def emit_batch(self, records: Sequence[logging.LogRecord]) -> None:
        """Persist ``records``. Called from the handler's thread, never a request's."""
        ...


def redact(text: str) -> str:
    """Mask credentials: auth headers, cookies, bearer tokens, key=value secrets, URL passwords."""
    text = _HEADER_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    text = _BEARER_RE.sub(f"Bearer {REDACTED}", text)
    text = _URL_CRED_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}:{REDACTED}@", text)
    return _SECRET_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", text)


def redact_record(record: logging.LogRecord) -> None:
    """Mask ``record`` in place: the message, the traceback text and any extra attributes."""
    record.msg = redact(record.getMessage())
    record.args = None
    if record.exc_text:
        record.exc_text = redact(record.exc_text)
    for key, value in list(record.__dict__.items()):
        if key in _STANDARD_ATTRS:
            continue
        if _SENSITIVE_KEY_RE.search(key):
            record.__dict__[key] = REDACTED
        elif isinstance(value, str):
            record.__dict__[key] = redact(value)


class RedactionFilter(logging.Filter):
    """Filter form of :func:`redact_record`, for a handler that is not a :class:`QueueSinkHandler`.

    Mutates the shared record, so attach it to a handler that owns its records.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        redact_record(record)
        return True


class QueueSinkHandler(logging.handlers.QueueHandler):
    """Forward records to a :class:`LogSink` in batches from a listener thread."""

    def __init__(
        self,
        sink: LogSink,
        *,
        level: int = logging.INFO,
        capacity: int = DEFAULT_QUEUE_CAPACITY,
        batch_size: int = DEFAULT_BATCH_SIZE,
        flush_interval: float = DEFAULT_FLUSH_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(queue.Queue(maxsize=capacity))
        self.setLevel(level)
        self.sink = sink
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._dropped = 0
        self._failed_batches = 0
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.addFilter(self._not_own_record)

    @staticmethod
    def _not_own_record(record: logging.LogRecord) -> bool:
        name = record.name
        return not any(
            name == prefix or name.startswith(f"{prefix}.") for prefix in SKIPPED_LOGGER_PREFIXES
        )

    @property
    def dropped(self) -> int:
        """Records discarded because the queue was full."""
        return self._dropped

    @property
    def failed_batches(self) -> int:
        """Batches the sink raised on; their records are lost."""
        return self._failed_batches

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        # QueueHandler.prepare formats the message and traceback into a copy, so
        # the caller's record, shared with every other handler, stays untouched.
        record = super().prepare(record)
        if not getattr(record, "correlation_id", ""):
            record.correlation_id = correlation_id.get("")
        redact_record(record)
        return record

    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            with self._lock:
                self._dropped += 1

    # ── lifecycle ───────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="log-sink", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Flush what is queued and stop the thread; gives up after a few seconds."""
        thread, self._thread = self._thread, None
        if thread is None:
            return
        try:
            self.queue.put(_STOP, timeout=STOP_TIMEOUT_SECONDS)
        except queue.Full:
            return
        thread.join(STOP_TIMEOUT_SECONDS)

    def _run(self) -> None:
        stopping = False
        while not stopping:
            batch: list[logging.LogRecord] = []
            deadline: float | None = None
            while len(batch) < self.batch_size:
                timeout = self.flush_interval if deadline is None else deadline - time.monotonic()
                if timeout <= 0:
                    break
                try:
                    item = self.queue.get(timeout=timeout)
                except queue.Empty:
                    break
                if item is _STOP:
                    stopping = True
                    break
                batch.append(item)
                if deadline is None:
                    deadline = time.monotonic() + self.flush_interval
            if batch:
                self._flush(batch)

    def _flush(self, batch: list[logging.LogRecord]) -> None:
        try:
            self.sink.emit_batch(batch)
        except Exception:
            with self._lock:
                self._failed_batches += 1
            # This module's own logger is skipped by the handler, so a failing
            # sink cannot loop back into itself.
            logger.warning("Log sink failed; dropped %d record(s)", len(batch), exc_info=True)


def install_sink(
    sink: LogSink, *, level: int = logging.INFO, target: logging.Logger | None = None, **options
) -> QueueSinkHandler:
    """Attach a started :class:`QueueSinkHandler` for ``sink`` to ``target`` (root by default)."""
    handler = QueueSinkHandler(sink, level=level, **options)
    handler.start()
    (target if target is not None else logging.getLogger()).addHandler(handler)
    return handler


def uninstall_sink(handler: QueueSinkHandler, *, target: logging.Logger | None = None) -> None:
    """Detach ``handler`` and flush it."""
    (target if target is not None else logging.getLogger()).removeHandler(handler)
    handler.stop()


__all__ = [
    "LogSink",
    "QueueSinkHandler",
    "RedactionFilter",
    "install_sink",
    "redact",
    "redact_record",
    "uninstall_sink",
]
