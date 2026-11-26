"""Run one generated command: build the request, confirm, send, render."""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from typing import Any
from urllib.parse import urlencode

import click
import httpx

from simple_module_remote.commands.confirm import confirm_protected
from simple_module_remote.generate.context import RunContext
from simple_module_remote.generate.emit import (
    ERROR_BODY_CHARS,
    emit,
    print_error,
    render_values,
    say,
)
from simple_module_remote.generate.operations import Operation
from simple_module_remote.generate.params import json_response_schema, success_is_json
from simple_module_remote.generate.prepare import DEFAULT_CONTENT_TYPE, Prepared, prepare_request
from simple_module_remote.http.client import ApiClient
from simple_module_remote.http.errors import (
    EXIT_CLIENT_ERROR,
    EXIT_USAGE,
    ApiError,
    UnsafePathError,
    exit_code_for,
)
from simple_module_remote.http.pagination import iter_items, pagination_style
from simple_module_remote.output.sanitize import is_terminal

__all__ = ["RunContext", "run_operation"]

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
REDIRECT_MIN = 300
ERROR_MIN = 400


class _HttpFailureError(Exception):
    """A failed response met while paging; the response is already read."""

    def __init__(self, response: httpx.Response) -> None:
        super().__init__(f"HTTP {response.status_code}")
        self.response = response


def _dry_run(ctx: RunContext, op: Operation, prep: Prepared, values: dict[str, Any]) -> None:
    url = ctx.env.url.rstrip("/") + prep.path
    if prep.params:
        url += "?" + urlencode(prep.params, doseq=True)
    lines = [f"{op.method} {url}"]
    if prep.json is not None:
        lines.append(json.dumps(prep.json, indent=2, ensure_ascii=False))
    if op.body_kind == "multipart":
        lines += [f"upload {u}" for u in values.get("uploads") or ()]
        lines += [f"form {s}" for s in values.get("sets") or ()]
    elif op.body_kind == "raw" and values.get("body_file"):
        kind = values.get("content_type") or DEFAULT_CONTENT_TYPE
        lines.append(f"body-file {values['body_file']} ({kind})")
    for line in lines:
        ctx.stdout.write(line + "\n")


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
) -> None:
    style = pagination_style(op, json_response_schema(op, ctx.root))
    if style is None:
        raise click.UsageError("--all and --limit are not supported by this command")

    def fetch(params: dict) -> Any:
        response = client.request(op.method, prep.path, params=params)
        if response.status_code >= REDIRECT_MIN:
            raise _HttpFailureError(response)
        try:
            return response.json()
        except ValueError:
            raise ApiError(
                response.status_code, response.text[:ERROR_BODY_CHARS], "response is not JSON"
            ) from None

    show = is_terminal(ctx.stderr)

    def progress(count: int) -> None:
        if show:
            ctx.stderr.write(f"\rfetched {count}")
            ctx.stderr.flush()

    items = list(iter_items(fetch, style, prep.params, values.get("limit"), progress))
    if show:
        ctx.stderr.write("\n")
    render_values(ctx, items, values)


def _fail(ctx: RunContext, exc: ApiError) -> int:
    say(ctx, f"error: {exc.message}")
    if exc.body_text.strip():
        say(ctx, exc.body_text[:ERROR_BODY_CHARS])
    return exit_code_for(exc.status)


def _status_code(response: httpx.Response) -> int:
    # A leftover 3xx means the request itself has to change, not that the server failed.
    return (
        EXIT_CLIENT_ERROR
        if response.status_code < ERROR_MIN
        else exit_code_for(response.status_code)
    )


def _exchange(
    ctx: RunContext,
    client: ApiClient,
    op: Operation,
    prep: Prepared,
    values: dict[str, Any],
    *,
    paged: bool,
    stream: bool,
) -> int:
    if paged:
        try:
            _all_pages(ctx, client, op, prep, values)
        except _HttpFailureError as failure:
            print_error(ctx, failure.response)
            return _status_code(failure.response)
        return 0
    with _send(client, op, prep, stream) as response:
        if response.status_code >= REDIRECT_MIN:
            print_error(ctx, response)
            return _status_code(response)
        return emit(ctx, response, values)


def run_operation(ctx: RunContext, op: Operation, values: dict[str, Any]) -> int:
    """Execute ``op`` with click ``values``; returns the process exit code."""
    mutation = op.method not in SAFE_METHODS
    with ExitStack() as stack:
        try:
            prep = prepare_request(op, values, ctx.root, ctx.stdin, stack)
        except UnsafePathError as exc:
            raise click.UsageError(
                f"{exc}; a path value may not contain '/' or '..', because it would change "
                "which endpoint is called"
            ) from None
        if values.get("dry_run"):
            _dry_run(ctx, op, prep, values)
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
            say(ctx, f"[{ctx.env.name}]")
        is_get = op.method == "GET"
        paged = is_get and bool(values.get("all_pages") or values.get("limit"))
        stream = is_get and bool(values.get("out") or not success_is_json(op, ctx.root))
        try:
            with ctx.client_factory() as client:
                return _exchange(ctx, client, op, prep, values, paged=paged, stream=stream)
        except ApiError as exc:
            return _fail(ctx, exc)
        except httpx.HTTPError as exc:
            return _fail(ctx, ApiError(0, message=f"response failed: {type(exc).__name__}"))
        except OSError as exc:
            say(ctx, f"error: cannot write output: {exc.__class__.__name__}")
            return EXIT_USAGE
        except UnsafePathError as exc:
            raise click.UsageError(str(exc)) from None
