"""Diagnostic output must survive slow/closed pipes and repeated app builds."""

from __future__ import annotations

import errno
import io
from dataclasses import replace

import pytest
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel, _runner, print_diagnostics


@pytest.fixture(autouse=True)
def isolated_output(monkeypatch):
    monkeypatch.setattr(_runner, "_printed_diagnostics", set())


def finding(**changes):
    return replace(
        Diagnostic(
            DiagnosticLevel.WARNING,
            "SM003",
            "Page has no render call",
            "Demo",
            file="pages/Browse.tsx",
            suggestion="Add a render call",
        ),
        **changes,
    )


class SlowStream(io.StringIO):
    def __init__(self):
        super().__init__()
        self.attempts = 0
        self.flush_attempts = 0

    def write(self, text):
        self.attempts += 1
        if self.attempts in {1, 3}:
            raise BlockingIOError(errno.EAGAIN, "slow reader")
        return super().write(text[:17])

    def flush(self):
        self.flush_attempts += 1
        if self.flush_attempts == 1:
            raise BlockingIOError(errno.EAGAIN, "slow flush")
        super().flush()


def test_temporary_backpressure_preserves_full_details(monkeypatch):
    stream = SlowStream()
    monkeypatch.setattr(_runner.sys, "stderr", stream)
    print_diagnostics([finding()])
    output = stream.getvalue()
    assert output.count("[WARNING] Demo: Page has no render call") == 1
    assert "pages/Browse.tsx" in output
    assert "Suggestion: Add a render call" in output
    assert "Results: 0 error(s), 1 warning(s), 0 info; SM003=1" in output
    assert stream.flush_attempts == 2


@pytest.mark.parametrize("error", [BrokenPipeError, OSError, BlockingIOError])
def test_unwritable_stream_falls_back_once_with_bounded_wait(monkeypatch, caplog, error):
    class UnwritableStream(io.StringIO):
        def write(self, text):
            number = errno.EAGAIN if error is BlockingIOError else errno.EIO
            raise error(errno.EPIPE if error is BrokenPipeError else number, "unwritable")

    elapsed = [0.0]

    def advance(seconds):
        elapsed[0] += seconds

    monkeypatch.setattr(_runner.sys, "stderr", UnwritableStream())
    # Virtual time proves a permanently full pipe cannot hold boot indefinitely.
    import time

    monkeypatch.setattr(time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(time, "sleep", advance)
    print_diagnostics([finding(), finding(code="SM024")])
    assert len(caplog.records) == 1
    assert "diagnostics" in caplog.messages[0]
    assert "SM003=1, SM024=1" in caplog.messages[0]
    assert elapsed[0] <= 0.11


def test_fallback_logger_using_a_closed_pipe_cannot_abort_boot(monkeypatch):
    def broken(*args, **kwargs):
        raise BrokenPipeError(errno.EPIPE, "closed")

    stream = io.StringIO()
    monkeypatch.setattr(stream, "write", broken)
    monkeypatch.setattr(_runner.sys, "stderr", stream)
    monkeypatch.setattr(_runner.logger, "warning", broken)
    print_diagnostics([finding()])


def test_partially_accepted_write_is_not_repeated(monkeypatch):
    class PartialStream(io.StringIO):
        blocked = False

        def write(self, text):
            if not self.blocked:
                self.blocked = True
                super().write(text[:12])
                raise BlockingIOError(errno.EAGAIN, "partially accepted", 12)
            return super().write(text)

    stream = PartialStream()
    monkeypatch.setattr(_runner.sys, "stderr", stream)
    print_diagnostics([finding()])
    assert stream.getvalue().startswith("⚠ SM003 [WARNING] Demo: Page has no render call\n")
    assert stream.getvalue().count("Results:") == 1


def test_broken_pipe_on_flush_falls_back_once(monkeypatch, caplog):
    class BrokenFlushStream(io.StringIO):
        def flush(self):
            raise BrokenPipeError(errno.EPIPE, "closed during flush")

    monkeypatch.setattr(_runner.sys, "stderr", BrokenFlushStream())
    print_diagnostics([finding()])
    assert len(caplog.records) == 1
    assert "SM003=1" in caplog.messages[0]


def test_each_call_writes_all_findings_to_current_stderr(monkeypatch):
    for _ in range(2):
        stream = io.StringIO()
        monkeypatch.setattr(_runner.sys, "stderr", stream)
        print_diagnostics([finding(), finding(code="SM024")])
        output = stream.getvalue()
        assert output.count("[WARNING] Demo: Page has no render call") == 2
        assert "SM003=1, SM024=1" in output


def test_identical_diagnostics_are_printed_once_across_calls(capsys):
    original = finding()
    print_diagnostics([original, replace(original)], once=True)
    print_diagnostics([replace(original)], once=True)
    output = capsys.readouterr().err
    assert output.count("[WARNING] Demo: Page has no render call") == 1
    assert output.count("Results:") == 1
    assert "Results: 0 error(s), 1 warning(s), 0 info; SM003=1" in output


def test_different_codes_messages_and_locations_remain_visible(capsys):
    print_diagnostics(
        [
            finding(),
            finding(code="SM024", level=DiagnosticLevel.ERROR),
            finding(message="Another problem", level=DiagnosticLevel.INFO),
            finding(file="pages/Edit.tsx"),
            finding(module_name="Other"),
        ]
    )
    output = capsys.readouterr().err
    assert "Results: 1 error(s), 3 warning(s), 1 info; SM003=4, SM024=1" in output
    assert "pages/Edit.tsx" in output
    assert "Other: Page has no render call" in output


def test_a_new_process_does_not_inherit_deduplication(monkeypatch, capsys):
    import os

    pid = os.getpid()
    print_diagnostics([finding()], once=True)
    capsys.readouterr()
    monkeypatch.setattr(os, "getpid", lambda: pid + 1)
    print_diagnostics([finding()], once=True)
    assert "[WARNING] Demo: Page has no render call" in capsys.readouterr().err
