"""Boot records stay atomic on pipes and own their raw descriptors."""

import errno
import os
import select
import subprocess
import sys
import textwrap
from contextlib import suppress
from pathlib import Path

import pytest
from simple_module_core.diagnostics import _runner


def test_unicode_report_lines_survive_concurrent_stderr_writes():
    code = textwrap.dedent(
        """
        import sys
        import threading
        from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel, print_diagnostics

        ready = threading.Event()
        stop = threading.Event()

        def log():
            sys.stderr.write('log message\\n')
            ready.set()
            while not stop.is_set():
                sys.stderr.write('log message\\n')

        writer = threading.Thread(target=log)
        writer.start()
        assert ready.wait(2)
        try:
            for batch in range(10):
                print_diagnostics([
                    Diagnostic(DiagnosticLevel.WARNING, 'SM003',
                               f'{batch}:{i}:' + '€' * 80, 'Demo')
                    for i in range(150)
                ], once=True)
        finally:
            stop.set()
            writer.join(2)
        assert not writer.is_alive()
        """
    )
    # subprocess stderr is a real pipe, drained concurrently by communicate().
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=15,
        check=True,
    )
    lines = result.stderr.decode("utf-8").splitlines()
    assert "log message" in lines
    findings = [line for line in lines if line.startswith("⚠")]
    assert findings == [
        f"⚠ SM003 [WARNING] Demo: {batch}:{i}:" + "€" * 80
        for batch in range(10)
        for i in range(150)
    ]
    assert lines.count("Results: 0 error(s), 150 warning(s), 0 info; SM003=150") == 10
    assert all(
        line == "" or line == "log message" or line.startswith(("⚠", "Results:")) for line in lines
    )


@pytest.mark.parametrize("fallback", [False, True])
def test_oversized_unicode_records_are_bounded_and_newline_terminated(
    tmp_path, monkeypatch, fallback
):
    limit = 512 if fallback else getattr(select, "PIPE_BUF", 512)
    if fallback:
        monkeypatch.delattr(select, "PIPE_BUF", raising=False)
    records = []
    write = os.write

    def record_write(fd, data):
        records.append(data)
        return write(fd, data)

    path = tmp_path / "stderr"
    with path.open("w", encoding="utf-8") as stream:
        monkeypatch.setattr(_runner.sys, "stderr", stream)
        monkeypatch.setattr(_runner.os, "write", record_write)
        _runner._write_report("start\n" + "€" * limit + "\nend\n", isolate=True)
    assert len(records) == 3
    assert all(len(record) <= limit and record.endswith(b"\n") for record in records)
    assert path.read_text(encoding="utf-8") == "start\n" + "€" * ((limit - 1) // 3) + "\nend\n"


@pytest.mark.parametrize("console_ownership", [False, True])
def test_many_reports_release_every_duplicate(monkeypatch, console_ownership):
    dup = os.dup
    fdopen = os.fdopen
    owned = []

    def track_dup(fd):
        duplicate = dup(fd)
        owned.append(duplicate)
        return duplicate

    def console_fdopen(fd, *args, **kwargs):
        # WindowsConsoleIO does not close a supplied fd when its wrapper closes.
        return fdopen(fd, *args, **kwargs, closefd=False)

    with Path(os.devnull).open("w", encoding="utf-8") as stream:
        monkeypatch.setattr(_runner.sys, "stderr", stream)
        monkeypatch.setattr(_runner.os, "dup", track_dup)
        if console_ownership:
            monkeypatch.setattr(_runner.os, "fdopen", console_fdopen)
        try:
            for _ in range(1200):
                _runner._write_report("⚠ Unicode report €\n", isolate=True)
                with pytest.raises(OSError) as closed:
                    os.fstat(owned[-1])
                assert closed.value.errno == errno.EBADF
            assert len(owned) == 1200
            stream.write("still open\n")
            stream.flush()
        finally:
            # Close leaked descriptors if the regression assertion fails.
            for fd in set(owned):
                with suppress(OSError):
                    os.close(fd)


@pytest.mark.parametrize("error", [BlockingIOError, BrokenPipeError, ValueError])
def test_failed_os_write_closes_duplicate_without_retry_or_shared_output(
    tmp_path, monkeypatch, caplog, error
):
    dup = os.dup
    owned = []
    attempts = []

    def track_dup(fd):
        duplicate = dup(fd)
        owned.append(duplicate)
        return duplicate

    def failed_write(fd, data):
        attempts.append(fd)
        raise error(errno.EAGAIN, "unwritable")

    path = tmp_path / "stderr"
    with path.open("w", encoding="utf-8") as stream:
        monkeypatch.setattr(_runner.sys, "stderr", stream)
        monkeypatch.setattr(_runner.os, "dup", track_dup)
        monkeypatch.setattr(_runner.os, "write", failed_write)
        _runner._write_report("first\nsecond\n", isolate=True)
        assert attempts == owned and len(attempts) == 1
        with pytest.raises(OSError) as closed:
            os.fstat(owned[0])
        assert closed.value.errno == errno.EBADF
    assert path.read_bytes() == b""
    assert caplog.records == []


def test_partial_os_write_is_not_retried(tmp_path, monkeypatch):
    write = os.write
    attempts = []

    def partial_write(fd, data):
        attempts.append(data)
        return write(fd, data[:2])

    path = tmp_path / "stderr"
    with path.open("w", encoding="utf-8") as stream:
        monkeypatch.setattr(_runner.sys, "stderr", stream)
        monkeypatch.setattr(_runner.os, "write", partial_write)
        _runner._write_report("first\nsecond\n", isolate=True)
    assert attempts == [b"first\n"]
    assert path.read_bytes() == b"fi"


def test_full_nonblocking_pipe_abandons_report_and_preserves_flags(monkeypatch):
    read_fd, write_fd = os.pipe()
    with os.fdopen(read_fd, "rb") as incoming:
        with os.fdopen(write_fd, "w", encoding="utf-8") as stream:
            os.set_blocking(write_fd, False)
            filled = 0
            with pytest.raises(BlockingIOError):
                while True:
                    filled += os.write(write_fd, b"x" * 512)
            monkeypatch.setattr(_runner.sys, "stderr", stream)
            _runner._write_report("⚠ report\n", isolate=True)
            assert not os.get_blocking(write_fd)
        assert incoming.read() == b"x" * filled
