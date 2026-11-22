"""Close helpers for Redis lease clients, including foreign-loop transports."""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

logger = logging.getLogger(__name__)


def _abort_transport(transport: Any) -> None:
    inner = getattr(getattr(transport, "_ssl_protocol", None), "_transport", None)
    target = inner if inner is not None else transport
    loop = getattr(target, "_loop", None)
    if loop is not None and not loop.is_closed() and loop.is_running():
        with suppress(RuntimeError):
            loop.call_soon_threadsafe(transport.abort)
        return
    if hasattr(target, "_sock"):
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
        return
    # uvloop transports expose PseudoSocket whose close() raises TypeError; abort instead.
    with suppress(RuntimeError, OSError, TypeError):
        transport.abort()


def close_foreign_transports(client: Any) -> None:
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
                _abort_transport(transport)
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
        connections.clear()
    if hasattr(pool, "_created_connections"):
        pool._created_connections = 0


async def close_redis_client(client: Any, *, foreign_owner: bool = False) -> None:
    """Close *client*, detaching foreign-loop transports before pool disconnect."""
    if foreign_owner:
        close_foreign_transports(client)
    try:
        close = getattr(client, "aclose", None) or client.close
        await close()
    except RuntimeError as exc:
        message = str(exc).lower()
        if foreign_owner and ("closed" in message or "different loop" in message):
            close_foreign_transports(client)
            return
        logger.warning("Redis lease client close failed (%s)", type(exc).__name__)
        raise
    except Exception as exc:
        logger.warning("Redis lease client close failed (%s)", type(exc).__name__)
        raise
