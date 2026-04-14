"""Tests for structured logging, correlation IDs, and request logging middleware."""

from __future__ import annotations

import json
import logging

import httpx
from simple_module_hosting.logging import (
    JsonFormatter,
    _CorrelationIdFilter,
    correlation_id,
    setup_logging,
)

# ── JsonFormatter ──────────────────────────────────────────────────────


class TestJsonFormatter:
    def test_basic_output_is_valid_json(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello world",
            args=None,
            exc_info=None,
        )
        record.correlation_id = ""  # type: ignore[attr-defined]
        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert parsed["message"] == "hello world"
        assert "timestamp" in parsed

    def test_includes_extra_fields(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="req",
            args=None,
            exc_info=None,
        )
        record.correlation_id = "abc-123"  # type: ignore[attr-defined]
        record.method = "GET"  # type: ignore[attr-defined]
        record.path = "/api/test"  # type: ignore[attr-defined]
        record.status_code = 200  # type: ignore[attr-defined]
        record.duration_ms = 12.5  # type: ignore[attr-defined]

        parsed = json.loads(formatter.format(record))
        assert parsed["correlation_id"] == "abc-123"
        assert parsed["method"] == "GET"
        assert parsed["path"] == "/api/test"
        assert parsed["status_code"] == 200
        assert parsed["duration_ms"] == 12.5

    def test_omits_absent_extra_fields(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="plain",
            args=None,
            exc_info=None,
        )
        record.correlation_id = ""  # type: ignore[attr-defined]
        parsed = json.loads(formatter.format(record))
        assert "method" not in parsed
        assert "status_code" not in parsed

    def test_includes_exception(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="failed",
            args=None,
            exc_info=exc_info,
        )
        record.correlation_id = ""  # type: ignore[attr-defined]
        parsed = json.loads(formatter.format(record))
        assert "exception" in parsed
        assert "ValueError: boom" in parsed["exception"]


# ── CorrelationIdFilter ────────────────────────────────────────────────


class TestCorrelationIdFilter:
    def test_injects_empty_string_by_default(self):
        filt = _CorrelationIdFilter()
        record = logging.LogRecord(
            name="x", level=logging.INFO, pathname="", lineno=0, msg="", args=None, exc_info=None
        )
        filt.filter(record)
        assert record.correlation_id == ""  # ty: ignore[unresolved-attribute]

    def test_injects_current_correlation_id(self):
        token = correlation_id.set("req-42")
        try:
            filt = _CorrelationIdFilter()
            record = logging.LogRecord(
                name="x",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="",
                args=None,
                exc_info=None,
            )
            filt.filter(record)
            assert record.correlation_id == "req-42"  # ty: ignore[unresolved-attribute]
        finally:
            correlation_id.reset(token)


# ── setup_logging ──────────────────────────────────────────────────────


class TestSetupLogging:
    def test_json_format(self):
        setup_logging(level="DEBUG", json_format=True)
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
        # Restore
        root.handlers.clear()

    def test_text_format(self):
        setup_logging(level="WARNING", json_format=False)
        root = logging.getLogger()
        assert root.level == logging.WARNING
        assert len(root.handlers) == 1
        assert not isinstance(root.handlers[0].formatter, JsonFormatter)
        root.handlers.clear()


# ── Correlation ID middleware (integration) ─────────────────────────────


class TestCorrelationIdMiddleware:
    async def test_generates_correlation_id(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        cid = resp.headers.get("x-correlation-id")
        assert cid is not None
        assert len(cid) > 0

    async def test_propagates_incoming_correlation_id(self, client: httpx.AsyncClient):
        resp = await client.get("/health", headers={"X-Correlation-ID": "my-trace-123"})
        assert resp.headers["x-correlation-id"] == "my-trace-123"

    async def test_different_requests_get_different_ids(self, client: httpx.AsyncClient):
        r1 = await client.get("/health")
        r2 = await client.get("/health")
        assert r1.headers["x-correlation-id"] != r2.headers["x-correlation-id"]


# ── Request logging middleware (integration) ────────────────────────────


class TestRequestLoggingMiddleware:
    async def test_logs_request_started_and_completed(
        self, client: httpx.AsyncClient, caplog: object
    ):
        import _pytest.logging

        assert isinstance(caplog, _pytest.logging.LogCaptureFixture)

        with caplog.at_level(logging.DEBUG, logger="simple_module.request"):
            await client.get("/dashboard", follow_redirects=False)

        messages = [r.message for r in caplog.records if r.name == "simple_module.request"]
        assert any("request.started" in m for m in messages)
        assert any("request.completed" in m for m in messages)

    async def test_skips_health_endpoints(self, client: httpx.AsyncClient, caplog: object):
        import _pytest.logging

        assert isinstance(caplog, _pytest.logging.LogCaptureFixture)

        with caplog.at_level(logging.INFO, logger="simple_module.request"):
            await client.get("/health")

        request_messages = [r for r in caplog.records if r.name == "simple_module.request"]
        assert len(request_messages) == 0

    async def test_log_records_have_extra_fields(self, client: httpx.AsyncClient, caplog: object):
        import _pytest.logging

        assert isinstance(caplog, _pytest.logging.LogCaptureFixture)

        with caplog.at_level(logging.INFO, logger="simple_module.request"):
            await client.get("/dashboard", follow_redirects=False)

        completed = [
            r
            for r in caplog.records
            if r.name == "simple_module.request" and r.message == "request.completed"
        ]
        assert len(completed) == 1
        record = completed[0]
        assert record.method == "GET"  # ty: ignore[unresolved-attribute]
        assert record.path == "/dashboard"  # ty: ignore[unresolved-attribute]
        assert hasattr(record, "status_code")
        assert hasattr(record, "duration_ms")
