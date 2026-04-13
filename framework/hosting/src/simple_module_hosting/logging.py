"""Structured logging — JSON formatter, correlation IDs, and setup helper."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


class _CorrelationIdFilter(logging.Filter):
    """Inject the current correlation ID into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id.get("")  # type: ignore[attr-defined]
        return True


class JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects.

    Standard fields: timestamp, level, logger, message, correlation_id.
    Extra keys (method, path, status_code, duration_ms, client_ip, user_id)
    are included when present on the record.
    """

    _EXTRA_KEYS = ("method", "path", "status_code", "duration_ms", "client_ip", "user_id")

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", ""),
        }

        for key in self._EXTRA_KEYS:
            value = getattr(record, key, None)
            if value is not None:
                log_obj[key] = value

        if record.exc_info and record.exc_info[0] is not None:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, default=str)


_TEXT_FORMAT = "%(asctime)s %(levelname)-8s [%(correlation_id)s] %(name)s — %(message)s"


def setup_logging(*, level: str = "INFO", json_format: bool = True) -> None:
    """Configure the root logger for structured output.

    Parameters
    ----------
    level:
        Log level name (DEBUG, INFO, WARNING, …).
    json_format:
        When *True* (the default) emit JSON lines; otherwise use a
        human-readable text format that still includes the correlation ID.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))

    handler.addFilter(_CorrelationIdFilter())

    root.addHandler(handler)
