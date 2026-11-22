"""Close helpers for Redis lease clients, including closed-owner transports."""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

logger = logging.getLogger(__name__)


def close_dead_transports(client: Any) -> None:
    """Release pooled sockets whose owning event loop has already closed."""
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
                raw_sock = getattr(transport, "_sock", None)
                if raw_sock is None:
                    wrapped = transport.get_extra_info("socket")
                    raw_sock = getattr(wrapped, "_sock", wrapped)
                if raw_sock is not None and hasattr(raw_sock, "close"):
                    with suppress(OSError):
                        raw_sock.close()
                for field, value in (("_sock", None), ("_closing", True)):
                    if hasattr(transport, field):
                        setattr(transport, field, value)
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


async def close_redis_client(client: Any, *, dead_owner: bool = False) -> None:
    """Close *client*, detaching dead-loop transports before pool disconnect."""
    if dead_owner:
        close_dead_transports(client)
    try:
        close = getattr(client, "aclose", None) or client.close
        await close()
    except RuntimeError as exc:
        if dead_owner and "closed" in str(exc).lower():
            close_dead_transports(client)
            return
        logger.warning("Redis lease client close failed (%s)", type(exc).__name__)
        raise
    except Exception as exc:
        logger.warning("Redis lease client close failed (%s)", type(exc).__name__)
        raise
