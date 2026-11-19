"""Isolated reports preserve stream encodings and encoded pipe boundaries."""

import os
import select
from concurrent.futures import ThreadPoolExecutor

import pytest
from simple_module_core.diagnostics import _runner


@pytest.mark.parametrize("encoding", ["utf-16", "utf-8-sig"])
def test_file_report_preserves_encoding_and_complete_long_lines(tmp_path, monkeypatch, encoding):
    report = "⚠ " + "€𐀀" * 3000 + "\nsecond\n"
    path = tmp_path / "stderr"
    with path.open("w", encoding=encoding) as stream:
        monkeypatch.setattr(_runner.sys, "stderr", stream)
        _runner._write_report(report, isolate=True)
    assert path.read_bytes().decode(encoding) == report


@pytest.mark.parametrize("encoding", ["utf-16", "utf-8-sig"])
@pytest.mark.parametrize("fallback", [False, True])
def test_pipe_report_preserves_encoding_when_truncated(monkeypatch, encoding, fallback):
    limit = 512 if fallback else getattr(select, "PIPE_BUF", 512)
    if fallback:
        monkeypatch.delattr(select, "PIPE_BUF", raising=False)
    records = []
    write = os.write

    def record_write(fd, data):
        records.append(data)
        return write(fd, data)

    read_fd, write_fd = os.pipe()
    with os.fdopen(read_fd, "rb") as incoming, ThreadPoolExecutor(max_workers=1) as reader:
        received = reader.submit(incoming.read)
        with os.fdopen(write_fd, "w", encoding=encoding) as stream:
            monkeypatch.setattr(_runner.sys, "stderr", stream)
            monkeypatch.setattr(_runner.os, "write", record_write)
            _runner._write_report("€𐀀" * limit + "\nsecond\n", isolate=True)
        output = received.result(timeout=2).decode(encoding)
    assert len(records) == 2
    assert all(len(record) <= limit for record in records)
    first, second = output.splitlines()
    assert first and ("€𐀀" * limit).startswith(first)
    assert second == "second"
    assert output.endswith("\n")


def test_ascii_stream_escapes_unencodable_diagnostics(tmp_path, monkeypatch):
    path = tmp_path / "stderr"
    with path.open("w", encoding="ascii") as stream:
        monkeypatch.setattr(_runner.sys, "stderr", stream)
        _runner._write_report("⚠ €\n", isolate=True)
    assert path.read_bytes() == b"\\u26a0 \\u20ac\n"
