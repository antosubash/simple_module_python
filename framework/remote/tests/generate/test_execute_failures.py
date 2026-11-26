import io
from pathlib import Path

import click
import httpx
import pytest
from simple_module_remote.config.environments import Environment
from simple_module_remote.generate.context import RunContext
from simple_module_remote.generate.execute import run_operation
from simple_module_remote.generate.operations import Operation, Param
from simple_module_remote.http.client import ApiClient

ROOT = {
    "paths": {
        "/api/users": {
            "get": {
                "responses": {
                    "200": {
                        "content": {"application/json": {"schema": {"type": "array", "items": {}}}}
                    }
                }
            }
        }
    }
}
PAGING = tuple(Param(n, "query", False, {"type": "integer"}, "") for n in ("page", "per_page"))


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def make_op(**kw) -> Operation:
    base = {
        "operation_id": "x", "method": "GET", "path": "/api/users", "group": "g", "name": "n",
        "params": (), "body_kind": "none", "body_schema": None, "summary": "",
        "description": "", "safe": False, "confirm": False, "token_capable": True,
    }  # fmt: skip
    base.update(kw)
    return Operation(**base)


def ctx_for(handler, *, tty=False, stdout=None, stderr=None) -> RunContext:
    env = Environment("prod", "https://app.example")
    return RunContext(
        env=env,
        client_factory=lambda: ApiClient(
            env, "tok", user_agent="t/1", transport=httpx.MockTransport(handler)
        ),
        is_tty=tty,
        stdout=stdout or io.StringIO(),
        stderr=stderr or io.StringIO(),
        stdin=io.StringIO(""),
        prompt=lambda t: "",
        root=ROOT,
    )


class Breaking(httpx.SyncByteStream):
    def __iter__(self):
        yield b"partial"
        raise httpx.ReadError("boom")


def broken(req):
    return httpx.Response(200, headers={"Content-Type": "image/png"}, stream=Breaking())


def test_paged_non_json_200_is_clean_error():
    ctx = ctx_for(lambda r: httpx.Response(200, text="<html>not json"))
    assert run_operation(ctx, make_op(params=PAGING), {"all_pages": True}) == 3
    assert "response is not JSON" in ctx.stderr.getvalue()


def test_paged_error_is_pretty_json():
    ctx = ctx_for(lambda r: httpx.Response(403, json={"detail": "no"}))
    assert run_operation(ctx, make_op(params=PAGING), {"all_pages": True}) == 4
    assert '"detail": "no"' in ctx.stderr.getvalue()


def test_mid_stream_error_leaves_no_partial_file(tmp_path: Path):
    target = tmp_path / "f.bin"
    ctx = ctx_for(broken)
    assert run_operation(ctx, make_op(), {"out": str(target)}) == 3
    assert "ReadError" in ctx.stderr.getvalue()
    assert list(tmp_path.iterdir()) == []


def test_out_replaces_atomically_on_success(tmp_path: Path):
    target = tmp_path / "f.bin"
    target.write_bytes(b"old")
    ctx = ctx_for(lambda r: httpx.Response(200, content=b"new"))
    assert run_operation(ctx, make_op(), {"out": str(target)}) == 0
    assert target.read_bytes() == b"new"
    assert [p.name for p in tmp_path.iterdir()] == ["f.bin"]


def test_out_to_missing_directory_is_clean_error(tmp_path: Path):
    ctx = ctx_for(lambda r: httpx.Response(200, content=b"x"))
    assert run_operation(ctx, make_op(), {"out": str(tmp_path / "no" / "f")}) == 1
    assert "cannot write output" in ctx.stderr.getvalue()


def test_limit_on_non_paged_op_is_usage_error():
    ctx = ctx_for(lambda r: httpx.Response(200, json=[]))
    with pytest.raises(click.UsageError):
        run_operation(ctx, make_op(), {"limit": 3})


def test_leftover_3xx_prints_location_exit_2():
    ctx = ctx_for(lambda r: httpx.Response(307, headers={"Location": "/api/else"}), tty=False)
    assert run_operation(ctx, make_op(method="POST"), {"dry_run": False}) == 2
    assert "Location: /api/else" in ctx.stderr.getvalue()


def test_dry_run_multipart_and_raw(tmp_path: Path):
    ctx = ctx_for(lambda r: pytest.fail("sent"))
    f = tmp_path / "d.txt"
    f.write_text("x")
    run_operation(
        ctx,
        make_op(method="POST", body_kind="multipart"),
        {"dry_run": True, "uploads": (f"file={f}",), "sets": ("a=b",)},
    )
    out = ctx.stdout.getvalue()
    assert f"upload file={f}" in out and "form a=b" in out
    raw = ctx_for(lambda r: pytest.fail("sent"))
    run_operation(
        raw, make_op(method="PUT", body_kind="raw"), {"dry_run": True, "body_file": str(f)}
    )
    assert f"body-file {f} (application/octet-stream)" in raw.stdout.getvalue()


def test_error_body_sanitized_on_tty_only():
    evil = "ok\x1b]0;pwned\x07\x1b[31mred\x1b[0m\x9b2J\x08end"
    tty = ctx_for(lambda r: httpx.Response(500, text=evil), stderr=Tty())
    run_operation(tty, make_op(), {})
    assert "\x1b" not in tty.stderr.getvalue() and "okred2Jend" in tty.stderr.getvalue()
    pipe = ctx_for(lambda r: httpx.Response(500, text=evil))
    run_operation(pipe, make_op(), {})
    assert "\x1b" in pipe.stderr.getvalue()


def test_text_response_sanitized_on_tty():
    ctx = ctx_for(
        lambda r: httpx.Response(
            200, text="hi\x1b[2Jthere", headers={"Content-Type": "text/plain"}
        ),
        stdout=Tty(),
    )
    run_operation(ctx, make_op(), {})
    assert ctx.stdout.getvalue() == "hithere"
