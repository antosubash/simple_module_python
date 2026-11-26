import io
from pathlib import Path

import click
import httpx
import pytest
from simple_module_remote.config.environments import Environment
from simple_module_remote.generate.context import RunContext
from simple_module_remote.generate.emit import ERROR_BODY_CHARS
from simple_module_remote.generate.execute import run_operation
from simple_module_remote.generate.operations import Param
from simple_module_remote.http.client import ApiClient

ROOT = {
    "paths": {
        "/api/x": {
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


def ctx_for(
    handler,
    *,
    tty=False,
    interactive=False,
    stdout=None,
    stderr=None,
    protected=False,
    factory=None,
    token="tok",
) -> RunContext:
    env = Environment("prod", "https://app.example", protected=protected)
    return RunContext(
        env=env,
        client_factory=factory
        or (
            lambda: ApiClient(env, token, user_agent="t/1", transport=httpx.MockTransport(handler))
        ),
        is_tty=tty,
        interactive=interactive,
        stdout=stdout or io.StringIO(),
        stderr=stderr or io.StringIO(),
        stdin=io.StringIO(""),
        prompt=lambda t: "",
        root=ROOT,
        login_hint="smdev --env prod login --token",
    )


class Breaking(httpx.SyncByteStream):
    def __iter__(self):
        yield b"partial"
        raise httpx.ReadError("boom")


def broken(req):
    return httpx.Response(200, headers={"Content-Type": "image/png"}, stream=Breaking())


def test_paged_non_json_200_is_clean_error(make_op):
    ctx = ctx_for(lambda r: httpx.Response(200, text="<html>not json"))
    assert run_operation(ctx, make_op(params=PAGING), {"all_pages": True}) == 3
    assert "response is not JSON" in ctx.stderr.getvalue()


def test_paged_error_is_pretty_json(make_op):
    ctx = ctx_for(lambda r: httpx.Response(403, json={"detail": "no"}))
    assert run_operation(ctx, make_op(params=PAGING), {"all_pages": True}) == 4
    assert '"detail": "no"' in ctx.stderr.getvalue()


def test_mid_stream_error_leaves_no_partial_file(tmp_path: Path, make_op):
    target = tmp_path / "f.bin"
    ctx = ctx_for(broken)
    assert run_operation(ctx, make_op(), {"out": str(target)}) == 3
    assert "ReadError" in ctx.stderr.getvalue()
    assert list(tmp_path.iterdir()) == []


def test_out_replaces_atomically_on_success(tmp_path: Path, make_op):
    target = tmp_path / "f.bin"
    target.write_bytes(b"old")
    ctx = ctx_for(lambda r: httpx.Response(200, content=b"new"))
    assert run_operation(ctx, make_op(), {"out": str(target)}) == 0
    assert target.read_bytes() == b"new"
    assert [p.name for p in tmp_path.iterdir()] == ["f.bin"]


def test_out_to_missing_directory_is_clean_error(tmp_path: Path, make_op):
    ctx = ctx_for(lambda r: httpx.Response(200, content=b"x"))
    assert run_operation(ctx, make_op(), {"out": str(tmp_path / "no" / "f")}) == 1
    assert "cannot write output" in ctx.stderr.getvalue()


def test_limit_on_non_paged_op_is_usage_error(make_op):
    ctx = ctx_for(lambda r: httpx.Response(200, json=[]))
    with pytest.raises(click.UsageError):
        run_operation(ctx, make_op(), {"limit": 3})


def test_leftover_3xx_prints_location_exit_2(make_op):
    ctx = ctx_for(lambda r: httpx.Response(307, headers={"Location": "/api/else"}), tty=False)
    assert run_operation(ctx, make_op(method="POST"), {"dry_run": False}) == 2
    assert "Location: /api/else" in ctx.stderr.getvalue()


def test_dry_run_multipart_and_raw(tmp_path: Path, make_op):
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


def test_error_body_sanitized_on_tty_only(make_op, make_tty):
    evil = "ok\x1b]0;pwned\x07\x1b[31mred\x1b[0m\x9b2J\x08end"
    tty = ctx_for(lambda r: httpx.Response(500, text=evil), stderr=make_tty())
    run_operation(tty, make_op(), {})
    assert "\x1b" not in tty.stderr.getvalue() and "okred2Jend" in tty.stderr.getvalue()
    pipe = ctx_for(lambda r: httpx.Response(500, text=evil))
    run_operation(pipe, make_op(), {})
    assert "\x1b" in pipe.stderr.getvalue()


def test_text_response_sanitized_on_tty(make_op, make_tty):
    ctx = ctx_for(
        lambda r: httpx.Response(
            200, text="hi\x1b[2Jthere", headers={"Content-Type": "text/plain"}
        ),
        stdout=make_tty(),
    )
    run_operation(ctx, make_op(), {})
    assert ctx.stdout.getvalue() == "hithere"


def test_dry_run_refuses_unsafe_path_value(make_op):
    ctx = ctx_for(lambda r: httpx.Response(200, json={}))
    op = make_op(
        method="DELETE",
        path="/api/users/{user_id}",
        params=(Param("user_id", "path", True, {"type": "string"}, ""),),
    )
    with pytest.raises(click.UsageError, match="may not contain"):
        run_operation(ctx, op, {"p_user_id": "a/b", "dry_run": True})
    assert ctx.stdout.getvalue() == ""


def test_confirmation_needs_stdin_and_stderr_not_stdout_tty(make_op):
    # stdout is a terminal but nothing can answer a prompt: refuse, never block.
    ctx = ctx_for(
        lambda r: httpx.Response(200, json={}), tty=True, interactive=False, protected=True
    )
    with pytest.raises(click.UsageError, match="--yes"):
        run_operation(ctx, make_op(method="DELETE"), {})


def test_piped_stdout_still_prompts_when_interactive(make_op):
    answers = []
    ctx = ctx_for(
        lambda r: httpx.Response(200, json={}), tty=False, interactive=True, protected=True
    )
    ctx.prompt = lambda text: answers.append(text) or "prod"
    assert run_operation(ctx, make_op(method="DELETE"), {}) == 0
    assert answers


def test_missing_credentials_fail_before_the_prompt(make_op):
    prompts = []

    def no_credentials():
        raise click.ClickException("no stored credentials")

    ctx = ctx_for(None, interactive=True, protected=True, factory=no_credentials)
    ctx.prompt = lambda text: prompts.append(text) or "prod"
    with pytest.raises(click.ClickException, match="no stored credentials"):
        run_operation(ctx, make_op(method="DELETE"), {})
    assert prompts == []


def test_unauthorized_prints_login_hint(make_op):
    ctx = ctx_for(lambda r: httpx.Response(401, json={}))
    assert run_operation(ctx, make_op(), {}) == 4
    assert "smdev --env prod login --token" in ctx.stderr.getvalue()


REFLECTED = "tok-reflected-1234"


def test_reflected_token_is_redacted_from_diagnostics(make_op):
    for handler in (
        lambda r: httpx.Response(401, text=f"Authorization: Bearer {REFLECTED}"),
        lambda r: httpx.Response(403, json={"echo": f"Bearer {REFLECTED}"}),
        lambda r: httpx.Response(302, headers={"Location": f"https://x.example/?t={REFLECTED}"}),
    ):
        ctx = ctx_for(handler, token=REFLECTED)
        run_operation(ctx, make_op(method="POST", safe=True), {})
        shown = ctx.stderr.getvalue()
        assert REFLECTED not in shown and "[redacted]" in shown


def test_token_straddling_the_truncation_cut_does_not_leak(make_op):
    body = "x" * (ERROR_BODY_CHARS - 5) + REFLECTED + "tail"
    ctx = ctx_for(lambda r: httpx.Response(500, text=body), token=REFLECTED)
    run_operation(ctx, make_op(), {})
    assert REFLECTED[:4] not in ctx.stderr.getvalue().replace("[redacted]", "")
    paged = ctx_for(lambda r: httpx.Response(200, text=body), token=REFLECTED)
    run_operation(paged, make_op(params=PAGING), {"all_pages": True})
    assert REFLECTED[:4] not in paged.stderr.getvalue().replace("[redacted]", "")


def test_reflected_token_in_content_type_is_redacted(make_op):
    kind = f"application/x-{REFLECTED}"
    ctx = ctx_for(
        lambda r: httpx.Response(200, headers={"Content-Type": kind}, content=b"\x00"),
        tty=True,
        token=REFLECTED,
    )
    assert run_operation(ctx, make_op(), {}) == 1
    assert REFLECTED not in ctx.stderr.getvalue()


@pytest.mark.parametrize("flag", [{"all_pages": True}, {"limit": 3}])
def test_all_or_limit_with_out_is_refused_before_sending(make_op, tmp_path, flag):
    sent = []
    ctx = ctx_for(lambda r: sent.append(r) or httpx.Response(200, json=[]))
    with pytest.raises(click.UsageError):
        run_operation(ctx, make_op(params=PAGING), {"out": str(tmp_path / "f"), **flag})
    assert sent == []
