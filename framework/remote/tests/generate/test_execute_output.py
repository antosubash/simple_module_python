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


@pytest.mark.parametrize("flags", [{"output": "id"}, {"quiet": True}])
def test_id_mode_refuses_bodies_it_cannot_render(execute_harness, make_op, flags):
    binary = httpx.Response(200, content=b"\x00\x01", headers={"Content-Type": "image/png"})
    h = execute_harness(lambda r: binary)
    with pytest.raises(click.ClickException, match="cannot be used here"):
        h.run(make_op(), **flags)
    assert h.out.getvalue() == ""
    broken = httpx.Response(
        200, content=b"not json at all", headers={"Content-Type": "application/json"}
    )
    h = execute_harness(lambda r: broken)
    with pytest.raises(click.ClickException, match="cannot be used here"):
        h.run(make_op(), **flags)
    assert h.out.getvalue() == ""


def test_id_mode_on_an_empty_200_is_an_error_not_silence(execute_harness, make_op):
    h = execute_harness(
        lambda r: httpx.Response(200, content=b"", headers={"Content-Type": "application/json"})
    )
    with pytest.raises(click.ClickException, match="empty"):
        h.run(make_op(), output="id")
    assert h.run(make_op()) == 0  # without id mode an empty body is still fine
    h = execute_harness(lambda r: httpx.Response(204))
    assert h.run(make_op(method="DELETE"), quiet=True) == 0  # 204 keeps its behaviour


@pytest.mark.parametrize("kind", ["text/vnd.api+json", "foo/bar+json", "application/problem+json"])
def test_any_plus_json_response_is_rendered_as_json(execute_harness, make_op, kind):
    h = execute_harness(
        lambda r: httpx.Response(200, content=b'{"id": 7}', headers={"Content-Type": kind})
    )
    assert h.run(make_op(), output="id") == 0
    assert h.out.getvalue() == "7\n"
