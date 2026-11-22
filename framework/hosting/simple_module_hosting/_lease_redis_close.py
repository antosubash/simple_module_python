"""Close helpers for Redis lease clients, including foreign-loop transports."""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import Future
from contextlib import suppress
from typing import Any

logger = logging.getLogger(__name__)


async def _noop() -> None:
    return None


def _fd_open(fd: int) -> bool:
    if fd < 0:
        return False
    try:
        os.fstat(fd)
    except OSError:
        return False
    return True


def _transport_fileno(transport: Any) -> int:
    raw_sock = getattr(transport, "_sock", None)
    if raw_sock is not None:
        with suppress(Exception):
            return int(raw_sock.fileno())
    with suppress(Exception):
        sock = transport.get_extra_info("socket")
        if sock is not None:
            return int(sock.fileno())
    return -1


def _close_selector_socket(target: Any, transport: Any, loop: Any) -> None:
    raw_sock = getattr(target, "_sock", None)
    if raw_sock is not None:
        if loop is not None and not loop.is_closed():
            with suppress(OSError, ValueError):
                fd = raw_sock.fileno()
                if fd != -1:
                    with suppress(Exception):
                        loop._remove_reader(fd)
                        loop._remove_writer(fd)
        with suppress(OSError):
            raw_sock.close()
    target._sock = None
    if hasattr(target, "_closing"):
        target._closing = True
    if target is not transport and hasattr(transport, "_closed"):
        transport._closed = True


async def _abort_on_running_loop(loop: Any, transport: Any) -> None:
    done: Future[None] = Future()

    def run_abort() -> None:
        try:
            transport.abort()
        finally:
            if not done.done():
                done.set_result(None)

    with suppress(RuntimeError):
        loop.call_soon_threadsafe(run_abort)
        await asyncio.wrap_future(done)


async def _abort_transport(transport: Any, *, owner_loop: Any = None, forked: bool = False) -> None:
    inner = getattr(getattr(transport, "_ssl_protocol", None), "_transport", None)
    target = inner if inner is not None else transport
    if forked:
        if hasattr(target, "_sock"):
            raw_sock = getattr(target, "_sock", None)
            if raw_sock is not None:
                with suppress(OSError):
                    raw_sock.close()
            target._sock = None
            if hasattr(target, "_closing"):
                target._closing = True
            if target is not transport and hasattr(transport, "_closed"):
                transport._closed = True
            return
        fd = _transport_fileno(target)
        if fd < 0:
            fd = _transport_fileno(transport)
        if fd >= 0:
            with suppress(OSError):
                os.close(fd)
        return

    loop = getattr(target, "_loop", None) or owner_loop
    if loop is not None and not loop.is_closed() and loop.is_running():
        await _abort_on_running_loop(loop, transport)
        return
    if hasattr(target, "_sock"):
        _close_selector_socket(target, transport, loop)
        return
    # uvloop transports expose PseudoSocket whose close() raises TypeError; abort instead.
    fd = _transport_fileno(transport)
    with suppress(RuntimeError, OSError, TypeError):
        transport.abort()
    if loop is not None and not loop.is_closed() and _fd_open(fd):
        try:
            await asyncio.to_thread(loop.run_until_complete, _noop())
        except RuntimeError:
            if loop.is_running():
                await _abort_on_running_loop(loop, transport)
        if _fd_open(fd):
            raise RuntimeError("Foreign Redis transport close still pending owner")


async def close_foreign_transports(
    client: Any, *, owner_loop: Any = None, forked: bool = False
) -> None:
    """Release pooled sockets whose owning event loop is unreachable."""
    pool = getattr(client, "connection_pool", None)
    if pool is None:
        return
    for attr in ("_available_connections", "_in_use_connections"):
        connections = getattr(pool, attr, None)
        if not connections:
            continue
        for conn in list(connections):
            writer = getattr(conn, "_writer", None)
            parser = getattr(conn, "_parser", None)
            stream = getattr(parser, "_stream", None) if parser is not None else None
            transport = getattr(writer, "transport", None) or getattr(stream, "_transport", None)
            if transport is not None:
                await _abort_transport(transport, owner_loop=owner_loop, forked=forked)
            if hasattr(parser, "on_disconnect"):
                parser.on_disconnect()
            for obj, field in (
                (conn, "_reader"),
                (conn, "_writer"),
                (parser, "_stream"),
                (stream, "_transport"),
            ):
                if obj is not None and hasattr(obj, field):
                    setattr(obj, field, None)
            if isinstance(connections, set):
                connections.discard(conn)
            else:
                connections.remove(conn)
    if hasattr(pool, "_created_connections"):
        pool._created_connections = 0


async def close_redis_client(
    client: Any,
    *,
    owner_loop: Any = None,
    foreign_owner: bool = False,
    forked: bool = False,
) -> None:
    """Close *client*, detaching foreign-loop transports before pool disconnect."""
    if foreign_owner:
        await close_foreign_transports(client, owner_loop=owner_loop, forked=forked)
    try:
        close = getattr(client, "aclose", None) or client.close
        await close()
    except RuntimeError as exc:
        message = str(exc).lower()
        if foreign_owner and ("closed" in message or "different loop" in message):
            await close_foreign_transports(client, owner_loop=owner_loop, forked=forked)
            return
        logger.warning("Redis lease client close failed (%s)", type(exc).__name__)
        raise
    except Exception as exc:
        logger.warning("Redis lease client close failed (%s)", type(exc).__name__)
        raise
