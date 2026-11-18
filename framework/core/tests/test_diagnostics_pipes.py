"""Exercise diagnostic delivery through actual buffered, backpressured pipes."""

import io
import os
import select
import threading
import time
from contextlib import contextmanager, suppress

import pytest
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel, _runner, print_diagnostics


@contextmanager
def stderr_pipe(monkeypatch, *, encoding="utf-8"):
    reader, writer = os.pipe()
    os.set_blocking(writer, False)
    stream = io.TextIOWrapper(
        io.BufferedWriter(io.FileIO(writer, "w"), buffer_size=4096),
        encoding=encoding,
        line_buffering=True,
    )
    monkeypatch.setattr(_runner.sys, "stderr", stream)
    try:
        yield reader, stream
    finally:
        with suppress(OSError, ValueError):
            stream.close()
        os.close(reader)


def fill_pipe(fd):
    total = 0
    while True:
        try:
            total += os.write(fd, b"x" * 4096)
        except BlockingIOError:
            return total


def finding(message="pipe report"):
    return Diagnostic(DiagnosticLevel.WARNING, "SM003", message, "Demo")


@pytest.mark.parametrize("repetitions", [20, 4000])
@pytest.mark.parametrize("prefix", ["", "older buffered output; "])
def test_slow_pipe_receives_unicode_report_exactly_once(monkeypatch, repetitions, prefix):
    message = "café 🌍 " * repetitions
    expected = (
        f"⚠ SM003 [WARNING] Demo: {message}\n\nResults: 0 error(s), 1 warning(s), 0 info; SM003=1\n"
    ).encode()
    with stderr_pipe(monkeypatch) as (reader, stream):
        prefill = fill_pipe(stream.fileno())
        stream.write(prefix)
        received = bytearray()
        stop = threading.Event()

        def drain():
            # Hold the initial full pipe briefly to exercise implicit-flush EAGAIN.
            stop.wait(0.02)
            while not stop.is_set() or select.select([reader], [], [], 0)[0]:
                if select.select([reader], [], [], 0.05)[0]:
                    received.extend(os.read(reader, 1024))
                    # A slow consumer forces successful short writes as well as EAGAIN.
                    stop.wait(0.001)

        thread = threading.Thread(target=drain)
        thread.start()
        try:
            print_diagnostics([finding(message)])
            stream.flush()
        finally:
            stop.set()
            thread.join(timeout=3)
        assert not thread.is_alive()
        assert received == b"x" * prefill + prefix.encode() + expected


@pytest.mark.parametrize("blocking", [False, True])
def test_full_pipe_obeys_deadline_and_restores_blocking_mode(monkeypatch, caplog, blocking):
    monkeypatch.setattr(_runner, "_OUTPUT_TIMEOUT", 0.05, raising=False)
    with stderr_pipe(monkeypatch) as (reader, stream):
        fill_pipe(stream.fileno())
        os.set_blocking(stream.fileno(), blocking)
        done = threading.Event()

        def emit():
            try:
                print_diagnostics([finding()])
            finally:
                done.set()

        started = time.monotonic()
        thread = threading.Thread(target=emit)
        thread.start()
        bounded = done.wait(0.5)
        elapsed = time.monotonic() - started
        # Unstick the old blocking implementation even when the assertion fails.
        os.read(reader, 4096)
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert bounded
        assert 0.03 <= elapsed < 0.5
        assert os.get_blocking(stream.fileno()) is blocking
        assert len(caplog.records) == 1


def test_successful_short_writes_share_one_deadline(monkeypatch, caplog):
    monkeypatch.setattr(_runner, "_OUTPUT_TIMEOUT", 0.04, raising=False)
    write = os.write
    pause = threading.Event()
    with stderr_pipe(monkeypatch) as (reader, stream):
        fd = stream.fileno()

        def short_write(target, payload):
            if target == fd:
                # Model a slow transport which always accepts a few bytes.
                pause.wait(0.01)
                payload = payload[:7]
            return write(target, payload)

        monkeypatch.setattr(_runner.os, "write", short_write)
        started = time.monotonic()
        print_diagnostics([finding("a" * 1000)])
        assert time.monotonic() - started < 0.3
        received = os.read(reader, 4096)
        assert received.startswith("⚠ SM003".encode())
        assert b"Results:" not in received
        assert len(caplog.records) == 1


def test_buffered_output_is_flushed_before_report_bytes(monkeypatch):
    with stderr_pipe(monkeypatch) as (reader, stream):
        stream.write("older buffered output; ")
        print_diagnostics([finding()])
        received = os.read(reader, 4096).decode()
        assert received.startswith("older buffered output; ⚠ SM003 [WARNING] Demo: pipe report")
        assert received.count("Results:") == 1


def test_pipe_uses_stream_encoding_with_backslash_escapes(monkeypatch):
    with stderr_pipe(monkeypatch, encoding="ascii") as (reader, _):
        print_diagnostics([finding("café 🌍")])
        assert os.read(reader, 4096) == (
            b"\\u26a0 SM003 [WARNING] Demo: caf\\xe9 \\U0001f30d\n\n"
            b"Results: 0 error(s), 1 warning(s), 0 info; SM003=1\n"
        )


def test_closed_stderr_and_closed_fallback_do_not_raise(monkeypatch):
    stream = io.StringIO()
    stream.close()
    monkeypatch.setattr(_runner.sys, "stderr", stream)

    def closed_logger(*args, **kwargs):
        raise ValueError("I/O operation on closed file")

    monkeypatch.setattr(_runner.logger, "warning", closed_logger)
    monkeypatch.setattr(_runner.logger, "info", closed_logger)
    print_diagnostics([finding()])
    print_diagnostics([])


def test_closed_pipe_stderr_falls_back_once(monkeypatch, caplog):
    with stderr_pipe(monkeypatch) as (_, stream):
        stream.close()
        print_diagnostics([finding()])
    assert len(caplog.records) == 1
    assert "SM003=1" in caplog.messages[0]
