"""Run one generated command: build the request, confirm, send, render."""

from __future__ import annotations

import json
from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlencode

import click
import httpx

from simple_module_remote.commands.confirm import confirm_protected
from simple_module_remote.config.environments import Environment
from simple_module_remote.generate.operations import Operation
from simple_module_remote.generate.params import json_response_schema, success_is_json
from simple_module_remote.generate.prepare import Prepared, prepare_request
from simple_module_remote.http.client import ApiClient
from simple_module_remote.http.errors import ApiError, UnsafePathError, exit_code_for
from simple_module_remote.http.pagination import iter_items, pagination_style
from simple_module_remote.output.render import OUTPUT_FORMATS, render

__all__ = ["RunContext", "run_operation"]

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
ERROR_BODY_CHARS = 500
CHUNK = 64 * 1024
REDIRECT_HINT = (
    "hint: this response followed a redirect; the token is not forwarded on redirects, "
    "so the redirect target rejected the request."
)


@dataclass
class RunContext:
    env: Environment
    client_factory: Callable[[], ApiClient]
    is_tty: bool
    stdout: TextIO
    stderr: TextIO
    stdin: TextIO
    prompt: Callable[[str], str]
    root: dict


def _is_binary(response: httpx.Response) -> bool:
    kind = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if not kind:
        return False
    return not (kind == "application/json" or kind.endswith("+json") or kind.startswith("text/"))


def _print_error(ctx: RunContext, response: httpx.Response) -> None:
    text = response.text
    ctx.stderr.write(f"error: HTTP {response.status_code}\n")
    if text.strip():
        try:
            ctx.stderr.write(json.dumps(json.loads(text), indent=2, ensure_ascii=False) + "\n")
        except ValueError:
            ctx.stderr.write(text[:ERROR_BODY_CHARS] + "\n")
    if response.status_code == 401 and ApiClient.was_redirected(response):
        ctx.stderr.write(REDIRECT_HINT + "\n")


def _dry_run(ctx: RunContext, op: Operation, prep: Prepared) -> None:
    url = ctx.env.url.rstrip("/") + prep.path
    if prep.params:
        url += "?" + urlencode(prep.params, doseq=True)
    ctx.stdout.write(f"{op.method} {url}\n")
    if prep.json is not None:
        ctx.stdout.write(json.dumps(prep.json, indent=2, ensure_ascii=False) + "\n")


def _write_file(response: httpx.Response, target: str) -> None:
    with Path(target).open("wb") as handle:
        for chunk in response.iter_bytes(CHUNK):
            handle.write(chunk)


def _write_stdout_bytes(ctx: RunContext, response: httpx.Response) -> bool:
    sink = getattr(ctx.stdout, "buffer", None)
    if sink is None:
        return False
    for chunk in response.iter_bytes(CHUNK):
        sink.write(chunk)
    sink.flush()
    return True


def _emit(ctx: RunContext, response: httpx.Response, values: dict[str, Any]) -> int:
    out = values.get("out")
    if response.status_code == 204:
        return 0
    if _is_binary(response) and not out:
        if ctx.is_tty or not _write_stdout_bytes(ctx, response):
            kind = response.headers.get("Content-Type", "binary")
            ctx.stderr.write(f"error: binary response ({kind}); use --out FILE to save it\n")
            return 1
        return 0
    if out:
        _write_file(response, out)
        ctx.stderr.write(f"wrote {out}\n")
        return 0
    response.read()
    if not response.content:
        return 0
    try:
        data: Any = response.json()
    except ValueError:
        ctx.stdout.write(response.text)
        return 0
    _render(ctx, data, values)
    return 0


def _render(ctx: RunContext, data: Any, values: dict[str, Any]) -> None:
    fmt = values.get("output")
    if fmt is not None and fmt not in OUTPUT_FORMATS:
        raise click.UsageError(f"--output must be one of: {', '.join(OUTPUT_FORMATS)}")
    columns = [c.strip() for c in (values.get("columns") or "").split(",") if c.strip()]
    render(
        data,
        fmt=fmt,
        columns=columns or None,
        quiet=bool(values.get("quiet")),
        is_tty=ctx.is_tty,
        out=ctx.stdout,
    )


@contextmanager
def _send(
    client: ApiClient, op: Operation, prep: Prepared, stream: bool
) -> Generator[httpx.Response]:
    if stream:
        with client.stream(op.method, prep.path, params=prep.params) as response:
            yield response
        return
    yield client.request(
        op.method,
        prep.path,
        params=prep.params,
        json=prep.json,
        files=prep.files,
        data=prep.data,
        content=prep.content,
        headers=prep.headers,
    )


def _all_pages(
    ctx: RunContext, client: ApiClient, op: Operation, prep: Prepared, values: dict[str, Any]
) -> int:
    style = pagination_style(op, json_response_schema(op, ctx.root))
    if style is None:
        if values.get("all_pages"):
            raise click.UsageError("--all is not supported by this command")
        return -1

    def fetch(params: dict) -> Any:
        response = client.request(op.method, prep.path, params=params)
        if response.status_code >= 400 or not response.content:
            raise ApiError(response.status_code, response.text)
        return response.json()

    show = bool(getattr(ctx.stderr, "isatty", lambda: False)())

    def progress(count: int) -> None:
        if show:
            ctx.stderr.write(f"\rfetched {count}")
            ctx.stderr.flush()

    items = list(iter_items(fetch, style, prep.params, values.get("limit"), progress))
    if show:
        ctx.stderr.write("\n")
    _render(ctx, items, values)
    return 0


def _fail(ctx: RunContext, exc: ApiError) -> int:
    ctx.stderr.write(f"error: {exc.message}\n")
    if exc.body_text.strip():
        ctx.stderr.write(exc.body_text[:ERROR_BODY_CHARS] + "\n")
    return exit_code_for(exc.status)


def run_operation(ctx: RunContext, op: Operation, values: dict[str, Any]) -> int:
    """Execute ``op`` with click ``values``; returns the process exit code."""
    mutation = op.method not in SAFE_METHODS
    with ExitStack() as stack:
        prep = prepare_request(op, values, ctx.root, ctx.stdin, stack)
        if values.get("dry_run"):
            _dry_run(ctx, op, prep)
            return 0
        confirm_protected(
            ctx.env,
            mutation=mutation,
            op_confirm=op.confirm,
            op_safe=op.safe,
            yes=bool(values.get("yes")),
            is_tty=ctx.is_tty,
            prompt=ctx.prompt,
            method=op.method,
            path=prep.path,
        )
        if mutation:
            ctx.stderr.write(f"[{ctx.env.name}]\n")
        paged = op.method == "GET" and bool(values.get("all_pages") or values.get("limit"))
        stream = op.method == "GET" and bool(values.get("out") or not success_is_json(op, ctx.root))
        try:
            with ctx.client_factory() as client:
                if paged:
                    code = _all_pages(ctx, client, op, prep, values)
                    if code >= 0:
                        return code
                with _send(client, op, prep, stream) as response:
                    if response.status_code >= 300:
                        response.read()
                        _print_error(ctx, response)
                        return exit_code_for(response.status_code)
                    return _emit(ctx, response, values)
        except ApiError as exc:
            return _fail(ctx, exc)
        except UnsafePathError as exc:
            raise click.UsageError(str(exc)) from None
