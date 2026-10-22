"""LogSink / QueueSinkHandler: batching, redaction, and never blocking (GH #537)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator, Sequence

import pytest
from simple_module_hosting.log_sinks import (
    REDACTED,
    QueueSinkHandler,
    install_sink,
    redact,
    uninstall_sink,
)


class Collector:
    def __init__(self) -> None:
        self.batches: list[list[logging.LogRecord]] = []

    def emit_batch(self, records: Sequence[logging.LogRecord]) -> None:
        self.batches.append(list(records))

    @property
    def messages(self) -> list[str]:
        return [str(r.msg) for batch in self.batches for r in batch]


class Blocked:
    """A sink that never returns until released."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.entered = threading.Event()

    def emit_batch(self, records: Sequence[logging.LogRecord]) -> None:
        self.entered.set()
        self.release.wait(10)


@pytest.fixture
def target() -> Iterator[logging.Logger]:
    log = logging.getLogger("hosting_log_sink_test")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    yield log
    log.handlers.clear()


def test_records_reach_the_sink_in_one_batch(target):
    sink = Collector()
    handler = install_sink(sink, target=target, flush_interval=0.05)
    for i in range(5):
        target.info("line %d", i)
    uninstall_sink(handler, target=target)
    assert sink.messages == [f"line {i}" for i in range(5)]
    assert len(sink.batches) == 1


def test_batches_are_capped(target):
    sink = Collector()
    handler = install_sink(sink, target=target, batch_size=3, flush_interval=0.05)
    for i in range(7):
        target.info("n%d", i)
    uninstall_sink(handler, target=target)
    assert [len(b) for b in sink.batches] == [3, 3, 1]


def test_level_threshold(target):
    sink = Collector()
    handler = install_sink(sink, level=logging.WARNING, target=target, flush_interval=0.05)
    target.info("quiet")
    target.warning("loud")
    uninstall_sink(handler, target=target)
    assert sink.messages == ["loud"]


def test_own_logger_and_sqlalchemy_are_skipped(target):
    sink = Collector()
    handler = install_sink(sink, target=target, flush_interval=0.05)
    for name in ("simple_module_hosting.log_sinks", "sqlalchemy.engine", "sqlalchemyx"):
        record = logging.LogRecord(name, logging.ERROR, __file__, 1, f"x-{name}", None, None)
        target.handle(record)
    uninstall_sink(handler, target=target)
    assert sink.messages == ["x-sqlalchemyx"]


def test_full_queue_drops_and_counts_without_blocking(target):
    sink = Blocked()
    handler = install_sink(sink, target=target, capacity=5, batch_size=1, flush_interval=0.01)
    target.info("first")
    assert sink.entered.wait(5)  # the listener is now stuck inside the sink
    started = time.monotonic()
    for i in range(100):
        target.info("burst %d", i)
    assert time.monotonic() - started < 2
    assert handler.dropped == 95  # 5 queued, the rest counted
    sink.release.set()
    uninstall_sink(handler, target=target)


def test_failing_sink_is_counted_and_does_not_raise(target):
    class Boom:
        def emit_batch(self, records):
            raise RuntimeError("down")

    handler = install_sink(Boom(), target=target, flush_interval=0.05)
    target.info("lost")
    uninstall_sink(handler, target=target)
    assert handler.failed_batches == 1


def test_secrets_are_masked_before_queueing_and_the_original_record_is_untouched(target):
    handler = QueueSinkHandler(Collector())
    target.addHandler(handler)
    record = logging.LogRecord(
        target.name,
        logging.INFO,
        __file__,
        1,
        "Authorization: Bearer abc.def password=hunter2",
        None,
        None,
    )
    record.session_token = "xyz"
    target.handle(record)
    queued = handler.queue.get_nowait()
    assert "abc.def" not in queued.msg and "hunter2" not in queued.msg
    assert queued.session_token == REDACTED
    assert "hunter2" in record.msg


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("GET / Authorization: Bearer abc123", "abc123"),
        ("Cookie: sid=s3cret; other=1", "s3cret"),
        ("login password=hunter2 ok", "hunter2"),
        ('{"access_token": "tok-999"}', "tok-999"),
        ("client_secret=shh&x=1", "shh"),
        ("sent Bearer eyJhbGciOi.payload.sig", "eyJhbGciOi"),
        ("headers={'Authorization': 'Basic Zm9vOmJhcg=='}", "Zm9vOmJhcg"),
    ],
)
def test_redact_masks(raw, secret):
    out = redact(raw)
    assert secret not in out
    assert REDACTED in out


def test_redact_keeps_ordinary_text():
    assert redact("user 42 logged in from 10.0.0.1") == "user 42 logged in from 10.0.0.1"


@pytest.mark.parametrize(
    "url",
    ["redis://user:s3cret@host:6379/0", "amqp://u:s3cret@mq/vhost", "postgresql://u:s3cret@db/x"],
)
def test_redact_masks_url_userinfo_password(url):
    out = redact(f"connecting to {url} now")
    assert "s3cret" not in out
    assert url.split("://")[0] in out and "@" in out


def test_redact_leaves_credential_free_urls_alone():
    assert redact("redis://localhost:6379/0") == "redis://localhost:6379/0"


TRICKY = [
    "redis://u:p@ss/w0rd-s3cret@host:6379/0",
    'login {"password": "two words s3cret"}',
    'escaped {\\"password\\": \\"s3cret\\"}',
    "jwt eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4 end",
    "key a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8 end",
    "Cookie: sid=s3cret; other=1",
]
SECRETS = ["s3cret", "w0rd", "two words", "eyJhbGciOiJIUzI1", "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"]


@pytest.mark.parametrize("raw", TRICKY)
def test_log_and_sentry_redact_identically(raw):
    from simple_module_hosting.sentry_scrub_text import scrub_text

    assert redact(raw) == scrub_text(raw)
    assert not any(s in redact(raw) for s in SECRETS)


def test_structured_extras_are_scrubbed_recursively() -> None:
    from simple_module_hosting.log_sinks import redact_record

    record = logging.makeLogRecord(
        {
            "msg": "x",
            "payload": {"password": "hunter2", "nested": [{"api_key": "k1"}], "ok": "fine"},
            "pair": ("authorization", "Bearer abc"),
            "opaque": object(),
        }
    )
    original = record.payload
    redact_record(record)
    dumped = repr((record.payload, record.pair))
    assert "hunter2" not in dumped
    assert "k1" not in dumped
    assert "abc" not in dumped
    assert record.payload["ok"] == "fine"
    assert original["password"] == "hunter2"  # the caller's object is untouched
