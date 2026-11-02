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
* **No feedback loop.** Records from this module's own logger, from
  ``sqlalchemy.*`` and any record emitted on the writer thread while a sink
  is writing (what a database sink itself triggers) are skipped.
"""

from __future__ import annotations

import logging
import logging.handlers
import queue
import threading
import time
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from simple_module_core.correlation import correlation_id

from simple_module_hosting.sentry_scrub import REDACTED, is_sensitive_key, scrub, scrub_text

logger = logging.getLogger(__name__)

DEFAULT_QUEUE_CAPACITY = 10_000
DEFAULT_BATCH_SIZE = 200
DEFAULT_FLUSH_INTERVAL_SECONDS = 1.0
STOP_TIMEOUT_SECONDS = 5.0
# Logger names whose records are never forwarded: our own, and the SQL layer a
# database sink writes through.
SKIPPED_LOGGER_PREFIXES: tuple[str, ...] = (__name__, "sqlalchemy")

_STOP = object()

_STANDARD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


@runtime_checkable
class LogSink(Protocol):
    """Where batches of log records end up."""

    def emit_batch(self, records: Sequence[logging.LogRecord]) -> None:
        """Persist ``records``. Called from the handler's thread, never a request's."""
        ...


def redact(text: str) -> str:
    """Mask credentials in ``text`` with the same bounded redactor Sentry events use."""
    return scrub_text(text)


def standard_extra_attrs(record: logging.LogRecord) -> dict[str, Any]:
    """The attributes a caller attached via ``extra=``, i.e. everything not a stock record field."""
    return {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS}


def redact_record(record: logging.LogRecord) -> None:
    """Mask ``record`` in place: the message, the traceback text and any extra attributes."""
    record.msg = redact(record.getMessage())
    record.args = None
    if record.exc_text:
        record.exc_text = redact(record.exc_text)
    for key, value in list(standard_extra_attrs(record).items()):
        if is_sensitive_key(key):
            record.__dict__[key] = REDACTED
        elif isinstance(value, str):
            record.__dict__[key] = redact(value)
        elif not (value is None or isinstance(value, bool | int | float)):
            # Mappings, sequences and arbitrary objects: the Sentry scrubber walks them
            # (sensitive keys at any depth, repr() of opaque objects) into a copy.
            record.__dict__[key] = scrub(value)


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
        self._writer = threading.local()
        self.addFilter(self._not_own_record)
        self.addFilter(self._not_from_writer_thread)

    def _not_from_writer_thread(self, record: logging.LogRecord) -> bool:
        # Anything logged while the sink writes (entity-change logs from the
        # insert itself, session or driver chatter) would be retained, written,
        # and logged again: drop it at the source.
        return not getattr(self._writer, "active", False)

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
        self._writer.active = True
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
