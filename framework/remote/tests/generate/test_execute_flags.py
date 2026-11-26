import io
import json

import click
import httpx
import pytest
from simple_module_remote.config.environments import Environment
from simple_module_remote.generate.context import RunContext
from simple_module_remote.generate.emit import CHUNK, ERROR_BODY_CHARS
from simple_module_remote.generate.execute import run_operation
from simple_module_remote.generate.operations import Param
from simple_module_remote.http.client import ApiClient

ROOT: dict = {"paths": {}}


class Harness:
    def __init__(self, handler, *, protected=False, tty=False, answers=()):
        self.requests: list[httpx.Request] = []
        self.out, self.err = io.StringIO(), io.StringIO()
        self.prompts: list[str] = []
        answer_iter = iter(answers)
        env = Environment("prod", "https://app.example", protected=protected)

        def wrapped(req: httpx.Request) -> httpx.Response:
            self.requests.append(req)
            return handler(req)

        def prompt(text: str) -> str:
            self.prompts.append(text)
            return next(answer_iter)

        self.ctx = RunContext(
            env=env,
            client_factory=lambda: ApiClient(
                env, "tok", user_agent="t/1", transport=httpx.MockTransport(wrapped)
            ),
            is_tty=tty,
            interactive=tty,
            stdout=self.out,
            stderr=self.err,
            stdin=io.StringIO(""),
            prompt=prompt,
            root=ROOT,
        )

    def run(self, op, **values) -> int:
        return run_operation(self.ctx, op, values)


def ok(req):
    return httpx.Response(200, json={"id": 1})


@pytest.fixture
def post(make_op):
    return make_op(
        method="POST",
        body_kind="json",
        body_schema={"type": "object", "properties": {"n": {"type": "integer"}}},
    )


@pytest.fixture
def download(make_op):
    return make_op(
        path="/api/files/{file_id}/download",
        params=(Param("file_id", "path", True, {"type": "string"}, ""),),
    )


def test_required_body_with_optional_fields_sends_empty_object(make_op, post):
    op = make_op(
        method="PUT",
        body_kind="json",
        body_required=True,
        body_schema={"type": "object", "properties": {"n": {"type": "integer"}}},
    )
    h = Harness(ok)
    assert h.run(op) == 0
    assert json.loads(h.requests[0].content) == {}
    dry = Harness(ok)
    dry.run(op, dry_run=True)
    assert dry.out.getvalue().splitlines()[1:] == ["{}"]


def test_optional_body_stays_absent(make_op):
    op = make_op(method="PUT", body_kind="json", body_schema={"type": "object"})
    h = Harness(ok)
    h.run(op)
    assert h.requests[0].content == b""


def test_required_array_body_without_input_is_an_error(make_op):
    op = make_op(method="POST", body_kind="json", body_required=True, body_schema={"type": "array"})
    with pytest.raises(click.UsageError, match="needs a request body"):
        Harness(ok).run(op)


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_path_value_is_refused_client_side(download, value):
    h = Harness(lambda r: pytest.fail("sent"))
    with pytest.raises(click.UsageError, match="file_id"):
        h.run(download, p_file_id=value)
    assert h.requests == []


def test_id_output_without_identifier_exits_1_with_message(make_op):
    h = Harness(lambda r: httpx.Response(200, json={"title": "t"}))
    with pytest.raises(click.ClickException, match="use -o json") as info:
        h.run(make_op(), output="id")
    assert info.value.exit_code == 1


class _Sink(io.RawIOBase):
    """A byte sink that logs writes in order, interleaved with the chunks the server yields."""

    def __init__(self, log):
        self.log = log

    def writable(self):
        return True

    def write(self, data):
        self.log.append(("write", len(data)))
        return len(data)


def _streamed(h, log):
    h.ctx.stdout = io.TextIOWrapper(
        io.BufferedWriter(_Sink(log), buffer_size=1), write_through=True
    )


@pytest.mark.parametrize("kind", ["application/octet-stream", "text/plain"])
def test_non_json_body_is_streamed_to_a_pipe_not_buffered(make_op, kind):
    log: list = []

    def body():
        for i in range(6):
            log.append(("pull", i))
            yield b"x" * CHUNK

    h = Harness(lambda r: httpx.Response(200, content=body(), headers={"Content-Type": kind}))
    _streamed(h, log)
    assert h.run(make_op()) == 0
    kinds = [k for k, _ in log]
    # Every chunk was written before the next one was pulled: nothing waited for the full body.
    assert kinds[:4] == ["pull", "write", "pull", "write"]
    assert sum(n for k, n in log if k == "write") == 6 * CHUNK


def test_oversized_json_is_refused_with_a_hint(make_op, monkeypatch):
    monkeypatch.setattr("simple_module_remote.generate.emit.MAX_RENDER_BYTES", 100)
    h = Harness(
        lambda r: httpx.Response(
            200, content=b'["' + b"a" * 500 + b'"]', headers={"Content-Type": "application/json"}
        )
    )
    assert h.run(make_op()) == 1
    assert "--out" in h.err.getvalue() and h.out.getvalue() == ""


def test_403_tenant_required_says_tenant_not_relogin(make_op):
    h = Harness(lambda r: httpx.Response(403, json={"detail": "tenant_required"}))
    h.ctx.login_hint = "smdev login --token"
    assert h.run(make_op()) == 4
    err = h.err.getvalue()
    assert "the server needs a tenant: tenant_required" in err
    assert "login" not in err


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_still_suggests_login(make_op, status):
    h = Harness(lambda r: httpx.Response(status, json={"detail": "Not authenticated"}))
    h.ctx.login_hint = "smdev login --token"
    assert h.run(make_op()) == 4
    assert "run `smdev login --token`" in h.err.getvalue()


def test_tenant_hint_redacts_a_token_straddling_the_cut(make_op):
    lead = "tenant " + "x" * (ERROR_BODY_CHARS - len("tenant ") - 2)
    h = Harness(lambda r: httpx.Response(403, json={"detail": lead + "tok-tail"}))  # token is "tok"
    assert h.run(make_op()) == 4
    hint = next(ln for ln in h.err.getvalue().splitlines() if ln.startswith("hint:"))
    body = hint.split("tenant: ", 1)[1].split("; pass")[0]
    assert body.endswith(("x[", "[redacted]"[: len(body) - body.rindex("[")]))
    assert "to" not in body.rsplit("x", 1)[-1]


def test_mutation_banner_names_the_tenant(post):
    h = Harness(ok)
    h.ctx.tenant = "acme"
    h.run(post, sets=("n=1",), yes=True)
    assert h.err.getvalue().startswith("[prod/acme]")


def test_confirmation_must_match_exactly(post):
    for answer in (" prod ", "prod ", " prod", "PROD"):
        h = Harness(ok, protected=True, tty=True, answers=[answer])
        with pytest.raises(click.UsageError):
            h.run(post, sets=("n=1",))
        assert h.requests == []
    h = Harness(ok, protected=True, tty=True, answers=["prod\n"])
    assert h.run(post, sets=("n=1",)) == 0
    assert h.prompts[0] == 'Type "prod" to run POST /api/x on prod (https://app.example)'


def test_sanitise_before_redact_defeats_interleaved_controls(make_op, make_tty):
    body = "bad " + "\x1b[0m".join("tok") + " end"  # the token "tok" split by escapes
    h = Harness(lambda r: httpx.Response(500, text=body))
    h.err = h.ctx.stderr = make_tty()
    assert h.run(make_op()) == 3
    assert "tok" not in h.err.getvalue() and "\x1b" not in h.err.getvalue()


def test_large_json_error_body_is_truncated_after_redaction(make_op):
    h = Harness(lambda r: httpx.Response(500, json={"detail": "y" * 5000}))
    h.run(make_op())
    assert len(h.err.getvalue()) < ERROR_BODY_CHARS + 100


def test_empty_out_is_a_usage_error(make_op):
    h = Harness(lambda r: pytest.fail("sent"))
    with pytest.raises(click.UsageError, match="--out"):
        h.run(make_op(), out="")
    assert h.requests == []
