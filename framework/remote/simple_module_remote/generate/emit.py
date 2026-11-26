"""Write a response to the terminal, a pipe or a file."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import click
import httpx

from simple_module_remote.generate.context import RunContext
from simple_module_remote.http.client import ApiClient
from simple_module_remote.http.errors import AUTH_STATUSES, ERROR_MIN
from simple_module_remote.output.render import OUTPUT_FORMATS, NoIdentifierError, render
from simple_module_remote.output.sanitize import sanitize_for

__all__ = ["emit", "print_error", "render_values", "say", "say_server"]

ERROR_BODY_CHARS = 500
CHUNK = 64 * 1024
FILE_MODE = 0o666
REDIRECT_HINT = (
    "hint: this response followed a redirect; the token is not forwarded on redirects, "
    "so the redirect target rejected the request."
)


def say(ctx: RunContext, text: str) -> None:
    """Write a line to stderr, safe for a terminal."""
    ctx.stderr.write(sanitize_for(ctx.stderr, text) + "\n")


def say_server(ctx: RunContext, text: str, *, limit: int | None = None) -> None:
    """Like :func:`say` for text the server sent: the token is stripped, then ``limit`` applied."""
    clean = ctx.redact(text)
    say(ctx, clean if limit is None else clean[:limit])


def is_binary(response: httpx.Response) -> bool:
    kind = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if not kind:
        return False
    return not (kind == "application/json" or kind.endswith("+json") or kind.startswith("text/"))


def _safe_location(ctx: RunContext, location: str) -> str:
    """The Location value, or a placeholder when it holds the token raw or percent-decoded."""
    for variant in (location, unquote(location), unquote(unquote(location))):
        if ctx.redact(variant) != variant:
            return "[redacted]"
    return location


def print_error(ctx: RunContext, response: httpx.Response) -> None:
    response.read()
    text = response.text
    say(ctx, f"error: HTTP {response.status_code}")
    if text.strip():
        try:
            # Redact the final text: JSON escapes decode back to the token when pretty-printed.
            say_server(ctx, json.dumps(json.loads(text), indent=2, ensure_ascii=False))
        except ValueError:
            say_server(ctx, text, limit=ERROR_BODY_CHARS)
    location = response.headers.get("Location")
    if location and response.status_code < ERROR_MIN:
        say(ctx, f"Location: {_safe_location(ctx, location)}")
    redirected = ApiClient.was_redirected(response)
    if response.status_code == 401 and redirected:
        say(ctx, REDIRECT_HINT)
    elif response.status_code in AUTH_STATUSES and ctx.login_hint:
        say(ctx, f"hint: the token may be missing, expired or lack access; run `{ctx.login_hint}`")


def _write_file(response: httpx.Response, target: str) -> None:
    """Stream to a temp file beside ``target`` and rename on success."""
    destination = Path(target)
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115
        "wb", dir=destination.parent, prefix=".smr-", delete=False
    )
    tmp = Path(handle.name)
    try:
        with handle:
            for chunk in response.iter_bytes(CHUNK):
                handle.write(chunk)
        mask = os.umask(0)
        os.umask(mask)
        tmp.chmod(FILE_MODE & ~mask)
        tmp.replace(destination)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def _write_stdout_bytes(ctx: RunContext, response: httpx.Response) -> bool:
    sink = getattr(ctx.stdout, "buffer", None)
    if sink is None:
        return False
    for chunk in response.iter_bytes(CHUNK):
        sink.write(chunk)
    sink.flush()
    return True


def render_values(ctx: RunContext, data: Any, values: dict[str, Any]) -> None:
    fmt = values.get("output")
    if fmt is not None and fmt not in OUTPUT_FORMATS:
        raise click.UsageError(f"--output must be one of: {', '.join(OUTPUT_FORMATS)}")
    columns = [c.strip() for c in (values.get("columns") or "").split(",") if c.strip()]
    try:
        render(
            data,
            fmt=fmt,
            columns=columns or None,
            quiet=bool(values.get("quiet")),
            is_tty=ctx.is_tty,
            out=ctx.stdout,
        )
    except NoIdentifierError as exc:
        raise click.ClickException(str(exc)) from None


def emit(ctx: RunContext, response: httpx.Response, values: dict[str, Any]) -> int:
    out = values.get("out")
    if response.status_code == 204:
        return 0
    if is_binary(response) and not out:
        if ctx.is_tty or not _write_stdout_bytes(ctx, response):
            kind = response.headers.get("Content-Type", "binary")
            say_server(ctx, f"error: binary response ({kind}); use --out FILE to save it")
            return 1
        return 0
    if out:
        _write_file(response, out)
        say(ctx, f"wrote {out}")
        return 0
    response.read()
    if not response.content:
        return 0
    try:
        data: Any = response.json()
    except ValueError:
        ctx.stdout.write(sanitize_for(ctx.stdout, response.text))
        return 0
    render_values(ctx, data, values)
    return 0
