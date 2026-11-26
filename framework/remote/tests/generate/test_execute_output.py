import io
import os

import click
import httpx
import pytest


def json_ok(data):
    return lambda req: httpx.Response(200, json=data)


def test_204_says_done_on_stderr(execute_harness, make_op):
    h = execute_harness(lambda r: httpx.Response(204))
    assert h.run(make_op(method="DELETE")) == 0
    assert h.out.getvalue() == "" and "done" in h.err.getvalue()


def test_csv_with_format_flags_is_refused(execute_harness, make_op):
    csv = httpx.Response(200, text="a,b\n1,2\n", headers={"Content-Type": "text/csv"})
    h = execute_harness(lambda r: csv)
    with pytest.raises(click.ClickException, match="not JSON"):
        h.run(make_op(), output="json")
    assert h.run(make_op()) == 0 and h.out.getvalue() == "a,b\n1,2\n"


def test_broken_pipe_is_quiet_and_exits_0(execute_harness, make_op, monkeypatch):
    class Pipe(io.StringIO):
        def write(self, text):
            raise BrokenPipeError

    h = execute_harness(json_ok({"a": 1}))
    h.ctx.stdout = Pipe()
    monkeypatch.setattr(os, "dup2", lambda *a: None)
    assert h.run(make_op()) == 0
    assert h.err.getvalue() == ""


def test_out_errors_are_readable(execute_harness, make_op, tmp_path):
    missing = execute_harness(json_ok({"a": 1}))
    assert missing.run(make_op(), out=str(tmp_path / "nope" / "x")) == 1
    assert "no such file or directory" in missing.err.getvalue()
    directory = execute_harness(json_ok({"a": 1}))
    assert directory.run(make_op(), out=str(tmp_path)) == 1
    assert "it is a directory" in directory.err.getvalue()
