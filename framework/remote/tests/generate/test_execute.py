import io
import json
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
        "/api/files/{file_id}/download": {
            "get": {"responses": {"200": {"content": {"application/octet-stream": {}}}}}
        },
        "/api/users": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"type": "object"}}
                            }
                        }
                    }
                }
            }
        },
    }
}


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


def test_dry_run_sends_nothing(post):
    h = Harness(lambda r: pytest.fail("sent"), protected=True)
    code = h.run(post, dry_run=True, sets=("n=3",))
    assert code == 0 and h.requests == []
    first, _, body = h.out.getvalue().partition("\n")
    assert first == "POST https://app.example/api/x"
    assert json.loads(body) == {"n": 3}


def test_protected_non_tty_requires_yes(post):
    h = Harness(ok, protected=True)
    with pytest.raises(click.UsageError, match="--yes"):
        h.run(post, sets=("n=1",))
    assert h.requests == []
    assert h.run(post, sets=("n=1",), yes=True) == 0


def test_protected_prompt_must_match_name(post):
    h = Harness(ok, protected=True, tty=True, answers=["nope", "prod"])
    with pytest.raises(click.UsageError):
        h.run(post, sets=("n=1",))
    assert h.requests == []
    assert h.prompts[0] == ('Type "prod" to run POST /api/x on prod (https://app.example):')
    assert h.run(post, sets=("n=1",)) == 0 and len(h.requests) == 1


def test_safe_post_skips_confirm(make_op, post):
    h = Harness(ok, protected=True)
    assert h.run(make_op(method="POST", safe=True)) == 0


def test_get_on_protected_needs_no_confirm_but_confirm_flag_does(make_op):
    h = Harness(ok, protected=True)
    assert h.run(make_op()) == 0
    with pytest.raises(click.UsageError):
        h.run(make_op(confirm=True))


def test_confirm_flag_on_get(make_op):
    h = Harness(ok, protected=True, tty=True, answers=["prod"])
    assert h.run(make_op(confirm=True)) == 0
    assert len(h.prompts) == 1


def test_mutation_prints_env_tag(make_op, post):
    h = Harness(ok)
    h.run(post, sets=("n=1",))
    assert h.err.getvalue().startswith("[prod]")
    g = Harness(ok)
    g.run(make_op())
    assert "[prod]" not in g.err.getvalue()


def binary(req):
    return httpx.Response(200, content=b"\x00\x01bin", headers={"Content-Type": "image/png"})


def test_binary_refused_on_tty_without_out(make_op):
    h = Harness(binary, tty=True)
    assert h.run(make_op()) == 1
    assert "--out" in h.err.getvalue()


def test_out_writes_file(tmp_path: Path, make_op):
    target = tmp_path / "f.bin"
    h = Harness(binary, tty=True)
    assert h.run(make_op(), out=str(target)) == 0
    assert target.read_bytes() == b"\x00\x01bin"


@pytest.fixture
def download(make_op):
    return make_op(
        path="/api/files/{file_id}/download",
        params=(Param("file_id", "path", True, {"type": "string"}, ""),),
    )


def test_binary_to_pipe_streams_raw_bytes(download):
    h = Harness(binary)
    sink = io.BytesIO()
    h.ctx.stdout = io.TextIOWrapper(sink, write_through=True)
    assert h.run(download, p_file_id="a b") == 0
    assert sink.getvalue() == b"\x00\x01bin"
    assert h.requests[0].url.raw_path == b"/api/files/a%20b/download"


def test_binary_without_byte_stdout_refused(download):
    h = Harness(binary)
    assert h.run(download, p_file_id="x") == 1


def test_path_value_with_slash_is_refused_not_sent(download):
    h = Harness(binary)
    with pytest.raises(click.UsageError):
        h.run(download, p_file_id="a/b")
    assert h.requests == []


def test_204_prints_nothing(make_op):
    h = Harness(lambda r: httpx.Response(204))
    assert h.run(make_op(method="DELETE", safe=True)) == 0
    assert h.out.getvalue() == ""


@pytest.mark.parametrize("size", [ERROR_BODY_CHARS, ERROR_BODY_CHARS + 1])
def test_non_json_error_body_truncated_at_limit(make_op, size):
    body = "<" + "x" * (size - 1)
    h = Harness(lambda r: httpx.Response(502, text=body))
    assert h.run(make_op()) == 3
    shown = h.err.getvalue().split("error: HTTP 502\n", 1)[1].rstrip("\n")
    assert shown == body[:ERROR_BODY_CHARS]
    assert len(shown) == ERROR_BODY_CHARS


def test_json_error_body_pretty(make_op):
    h = Harness(lambda r: httpx.Response(404, json={"detail": "nope"}))
    assert h.run(make_op()) == 5
    assert '"detail": "nope"' in h.err.getvalue()


def test_network_error_exit_3(make_op):
    def boom(req):
        raise httpx.ConnectError("down")

    h = Harness(boom)
    assert h.run(make_op()) == 3
    assert "request failed" in h.err.getvalue()


def test_401_after_redirect_hint(make_op):
    def handler(req):
        if req.url.host == "app.example":
            return httpx.Response(302, headers={"Location": "https://cdn.example/f"})
        return httpx.Response(401, text="no")

    h = Harness(handler)
    assert h.run(make_op(), out="/dev/null") == 4
    assert "redirect" in h.err.getvalue()


def test_query_and_json_output(make_op):
    op = make_op(
        path="/api/users",
        params=(
            Param("tag", "query", False, {"type": "array", "items": {}}, ""),
            Param("active", "query", False, {"type": "boolean"}, ""),
        ),
    )
    h = Harness(lambda r: httpx.Response(200, json=[{"id": 1}]))
    assert h.run(op, q_tag=("a", "b"), q_active=True) == 0
    assert str(h.requests[0].url).endswith("/api/users?tag=a&tag=b&active=true")
    assert json.loads(h.out.getvalue()) == [{"id": 1}]


def test_all_pages_paginates(make_op):
    op = make_op(
        path="/api/users",
        params=(
            Param("page", "query", False, {"type": "integer"}, ""),
            Param("per_page", "query", False, {"type": "integer"}, ""),
        ),
    )

    def handler(req):
        page = int(req.url.params["page"])
        return httpx.Response(200, json=[{"id": page}] if page < 3 else [])

    h = Harness(handler)
    assert h.run(op, all_pages=True, q_per_page=1) == 0
    assert [i["id"] for i in json.loads(h.out.getvalue())] == [1, 2]


def test_multipart_upload_and_closes(tmp_path: Path, make_op, post):
    f = tmp_path / "doc.txt"
    f.write_text("hi")
    h = Harness(ok)
    code = h.run(
        make_op(method="POST", body_kind="multipart"), uploads=(f"file={f}",), sets=("a=b",)
    )
    assert code == 0
    body = h.requests[0].content
    assert b'filename="doc.txt"' in body and b"hi" in body and b'name="a"' in body


def test_raw_body_file(tmp_path: Path, make_op):
    f = tmp_path / "b.bin"
    f.write_bytes(b"raw!")
    h = Harness(ok)
    h.run(make_op(method="PUT", body_kind="raw"), body_file=str(f))
    assert h.requests[0].content == b"raw!"
    assert h.requests[0].headers["content-type"] == "application/octet-stream"


def test_missing_required_body_fields(make_op, post):
    op = make_op(method="POST", body_kind="json", body_schema={"required": ["email"]})
    h = Harness(ok)
    with pytest.raises(click.UsageError, match="email"):
        h.run(op, sets=("a=1",))
