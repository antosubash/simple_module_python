import io
import os

import click
import httpx
import pytest
from simple_module_remote.config.environments import Environment
from simple_module_remote.generate.context import RunContext
from simple_module_remote.generate.execute import run_operation
from simple_module_remote.generate.operations import Param
from simple_module_remote.http.client import ApiClient


class H:
    """A RunContext over a mock transport; ``run`` returns the exit code."""

    def __init__(self, handler, root=None):
        self.requests: list[httpx.Request] = []
        self.out, self.err = io.StringIO(), io.StringIO()
        env = Environment("prod", "https://app.example")

        def wrapped(req):
            self.requests.append(req)
            return handler(req)

        self.ctx = RunContext(
            env=env,
            client_factory=lambda: ApiClient(
                env, "tok", user_agent="t/1", transport=httpx.MockTransport(wrapped)
            ),
            is_tty=False,
            stdout=self.out,
            stderr=self.err,
            stdin=io.StringIO(""),
            prompt=lambda t: "",
            root=root or {"paths": {}},
        )

    def run(self, op, **values) -> int:
        return run_operation(self.ctx, op, values)


def json_ok(data):
    return lambda req: httpx.Response(200, json=data)


def test_204_says_done_on_stderr(make_op):
    h = H(lambda r: httpx.Response(204))
    assert h.run(make_op(method="DELETE")) == 0
    assert h.out.getvalue() == "" and "done" in h.err.getvalue()


def test_csv_with_format_flags_is_refused(make_op):
    csv = httpx.Response(200, text="a,b\n1,2\n", headers={"Content-Type": "text/csv"})
    h = H(lambda r: csv)
    with pytest.raises(click.ClickException, match="not JSON"):
        h.run(make_op(), output="json")
    assert h.run(make_op()) == 0 and h.out.getvalue() == "a,b\n1,2\n"


def test_all_with_page_is_refused(make_op):
    op = make_op(
        params=tuple(
            Param(n, "query", False, {"type": "integer"}, "") for n in ("page", "per_page")
        )
    )
    root = {
        "paths": {
            "/api/x": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {"schema": {"type": "array", "items": {}}}
                            }
                        }
                    }
                }
            }
        }
    }
    h = H(json_ok([]), root)
    with pytest.raises(click.UsageError, match="page 1"):
        h.run(op, all_pages=True, q_page=2)
    assert h.requests == []


def test_broken_pipe_is_quiet_and_exits_0(make_op, monkeypatch):
    class Pipe(io.StringIO):
        def write(self, text):
            raise BrokenPipeError

    h = H(json_ok({"a": 1}))
    h.ctx.stdout = Pipe()
    monkeypatch.setattr(os, "dup2", lambda *a: None)
    assert h.run(make_op()) == 0
    assert h.err.getvalue() == ""


def test_out_errors_are_readable(make_op, tmp_path):
    missing = H(json_ok({"a": 1}))
    assert missing.run(make_op(), out=str(tmp_path / "nope" / "x")) == 1
    assert "no such file or directory" in missing.err.getvalue()
    directory = H(json_ok({"a": 1}))
    assert directory.run(make_op(), out=str(tmp_path)) == 1
    assert "it is a directory" in directory.err.getvalue()
