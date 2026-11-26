"""Write a response to the terminal, a pipe or a file."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import click
import httpx

from simple_module_remote.generate.context import RunContext
from simple_module_remote.http.client import ApiClient
from simple_module_remote.http.error_kinds import (
    detail_of,
    detail_text,
    schema_mismatch,
    token_problem,
)
from simple_module_remote.http.errors import AUTH_STATUSES, ERROR_MIN, SCHEMA_STALE_STATUSES
from simple_module_remote.output.render import (
    OUTPUT_FORMATS,
    NoIdentifierError,
    UnknownColumnError,
    render,
)
from simple_module_remote.output.sanitize import sanitize_for

__all__ = ["emit", "print_error", "render_values", "say", "say_server"]

ERROR_BODY_CHARS = 500
CHUNK = 64 * 1024
MAX_RENDER_BYTES = 64 * 1024 * 1024
FILE_MODE = 0o666
# The server's wording for a route only a browser session may call (checked before scopes).
_SESSION_ONLY = re.compile(
    r"browser session|session[- ]only|session required|tokens cannot be used|signed-in session"
)
REDIRECT_HINT = (
    "hint: this response followed a redirect; the token is not forwarded on redirects, "
    "so the redirect target rejected the request."
)


def say(ctx: RunContext, text: str) -> None:
    """Write a line to stderr, safe for a terminal."""
    ctx.stderr.write(sanitize_for(ctx.stderr, text) + "\n")


def _clean(ctx: RunContext, text: str) -> str:
    """Server text made safe for stderr: sanitised, then redacted in both forms."""
    return ctx.redact(sanitize_for(ctx.stderr, ctx.redact(text)))


def say_server(ctx: RunContext, text: str, *, limit: int | None = None) -> None:
    """Like :func:`say` for text the server sent: the token is stripped, then ``limit`` applied."""
    # Sanitise first, then redact both forms: control characters interleaved into the token
    # would otherwise be stripped afterwards and reassemble it on a terminal.
    clean = _clean(ctx, text)
    say(ctx, clean if limit is None else clean[:limit])


def _media_type(response: httpx.Response) -> str:
    return response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()


def is_binary(response: httpx.Response) -> bool:
    kind = _media_type(response)
    if not kind:
        return False
    return not (_json_type(kind) or kind.startswith("text/"))


def has_type(response: httpx.Response) -> bool:
    return bool(_media_type(response))


def _json_type(kind: str) -> bool:
    # Responses are read broadly: application/json and any */*+json. (Request media for the
    # schema side, operations.is_json_media, is stricter: application/*+json only.)
    return kind == "application/json" or kind.endswith("+json")


def is_json(response: httpx.Response) -> bool:
    return _json_type(_media_type(response))


def _read_capped(response: httpx.Response) -> bytes:
    """The body, read in chunks; refuses one larger than :data:`MAX_RENDER_BYTES`."""
    declared = response.headers.get("Content-Length", "")
    if declared.isascii() and declared.isdigit() and int(declared) > MAX_RENDER_BYTES:
        raise _TooLargeError
    chunks, size = [], 0
    for chunk in response.iter_bytes(CHUNK):
        size += len(chunk)
        if size > MAX_RENDER_BYTES:
            raise _TooLargeError
        chunks.append(chunk)
    return b"".join(chunks)


class _TooLargeError(Exception):
    pass


def _safe_location(ctx: RunContext, location: str) -> str:
    """The Location value, or a placeholder when it holds the token raw or percent-decoded."""
    for variant in (location, unquote(location), unquote(unquote(location))):
        if ctx.redact(variant) != variant:
            return "[redacted]"
    return location


def _auth_hint(ctx: RunContext, status: int, text: str) -> None:
    """Point at re-login only when the token itself is the problem."""
    detail = detail_text(text)
    lowered = detail.lower()
    shown = _clean(ctx, detail)[:ERROR_BODY_CHARS]  # sanitise, redact, then cut
    msg: str | None = None
    if "tenant" in lowered or "organisation" in lowered or "organization" in lowered:
        msg = (
            f"hint: the server needs a tenant: {shown}; pass --tenant or use a token pinned to one"
        )
    elif ctx.session_only or _SESSION_ONLY.search(lowered):
        cli = ctx.login_hint.split()[0] if ctx.login_hint else "the CLI"
        msg = f"hint: tokens cannot call this route; `{cli} api --session-only` lists such routes"
    elif "permission" in lowered or "scope" in lowered:
        msg = "hint: the token lacks the permission named above; create one with the needed scopes"
    elif ctx.login_hint and token_problem(status, detail_of(text)):
        msg = (
            f"hint: the token may be missing or expired; run `{ctx.login_hint}` "
            "(or pipe it to --token-stdin)"
        )
    if msg is not None:
        say(ctx, msg)


def print_error(ctx: RunContext, response: httpx.Response) -> None:
    response.read()
    text = response.text
    say(ctx, f"error: HTTP {response.status_code}")
    if text.strip():
        try:
            # Redact the final text: JSON escapes decode back to the token when pretty-printed.
            say_server(
                ctx,
                json.dumps(json.loads(text), indent=2, ensure_ascii=False),
                limit=ERROR_BODY_CHARS,
            )
        except ValueError:
            say_server(ctx, text, limit=ERROR_BODY_CHARS)
    location = response.headers.get("Location")
    if location and response.status_code < ERROR_MIN:
        say(ctx, f"Location: {_safe_location(ctx, location)}")
    redirected = ApiClient.was_redirected(response)
    if response.status_code == 401 and redirected:
        say(ctx, REDIRECT_HINT)
    elif response.status_code in AUTH_STATUSES:
        _auth_hint(ctx, response.status_code, text)
    elif (
        response.status_code in SCHEMA_STALE_STATUSES
        and ctx.schema_hint
        and schema_mismatch(response.status_code, text)
    ):
        say(ctx, ctx.schema_hint)


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
    except (NoIdentifierError, UnknownColumnError) as exc:
        # Column names come from the response: sanitise and redact them like any server text.
        raise click.ClickException(_clean(ctx, str(exc))[:ERROR_BODY_CHARS]) from None


def _id_mode(values: dict[str, Any]) -> bool:
    return values.get("output") == "id" or bool(values.get("quiet"))


def _refuse_render_flags(values: dict[str, Any]) -> None:
    """-o/-q/--columns format JSON; refuse them for a body that is not (a CSV export)."""
    given = [
        f
        for f, key in (("-o", "output"), ("-q", "quiet"), ("--columns", "columns"))
        if values.get(key)
    ]
    if given:
        raise click.ClickException(
            f"{'/'.join(given)} cannot be used here: the response is not JSON "
            "(redirect stdout or use --out FILE)"
        )


def emit(ctx: RunContext, response: httpx.Response, values: dict[str, Any]) -> int:
    out = values.get("out")
    if response.status_code == 204:
        say(ctx, "done (204 No Content)")
        return 0
    non_json = has_type(response) and not is_json(response)
    if non_json and not out:
        _refuse_render_flags(values)
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
    streamable = not ctx.is_tty and non_json
    # A pipe gets a non-JSON body chunk by chunk; a terminal needs it sanitized instead.
    if streamable and _write_stdout_bytes(ctx, response):
        return 0
    try:
        body = _read_capped(response)
    except _TooLargeError:
        say(ctx, "error: response is too large to render; use --out FILE to save it")
        return 1
    if not body:
        if _id_mode(values):  # no body, no identifiers: not a silent success
            raise click.ClickException("-o id/-q cannot be used here: the response is empty")
        return 0
    try:
        data: Any = json.loads(body)
    except ValueError:
        _refuse_render_flags(values)  # identifiers/columns cannot come from a body that is not JSON
        text = body.decode(response.charset_encoding or "utf-8", errors="replace")
        ctx.stdout.write(sanitize_for(ctx.stdout, text))
        return 0
    render_values(ctx, data, values)
    return 0
