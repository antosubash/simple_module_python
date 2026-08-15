"""Commit the request's unit of work before the response leaves the server.

``get_db`` is a FastAPI ``yield`` dependency, and FastAPI runs a yield
dependency's exit code *after* the response has been delivered. Committing
there means a client that creates a row and immediately references it by id in
a second request loses the race: the create's ``201`` reaches the client before
the create's commit runs, so the follow-up request opens a fresh session, finds
nothing, and 404s. It is deterministic rather than flaky — the follow-up
request reliably beats the post-response commit — which is why a seed script
publishes 0 pages on its first pass and all of them on a second, identical one.
See GH #257.

This module moves the commit to the last point that is still *inside* the
request: the ASGI ``http.response.start`` message. Nothing has reached the
client yet, so a failure there can still become a 500, and every caller —
seeds, provisioning scripts, integration tests, single-run k8s jobs — gets the
guarantee without changing a line of endpoint code.

A session is finalized exactly once. Whichever runs first wins and the other
becomes a no-op, so the framework stays correct when the middleware is absent
(a bare ``get_db``, a WebSocket, a test calling the dependency directly) and on
the error path, where FastAPI unwinds the dependency — rolling it back —
*before* the error response is sent.
"""

from __future__ import annotations

import json
import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from simple_module_db.listeners import SESSION_HAS_WRITES_KEY

logger = logging.getLogger("simple_module.db")

REQUEST_SESSIONS_KEY = "sm_db_sessions"
"""Key under ASGI ``scope["state"]`` holding the sessions opened this request."""

SESSION_START_KEY = "sm_db_started_at"
"""``session.info`` key carrying the perf-counter reading taken at open."""

_FINALIZED_KEY = "sm_db_finalized"

_INTERNAL_ERROR_BODY = json.dumps({"detail": "Internal Server Error"}).encode()


def _elapsed_ms(session: AsyncSession) -> float:
    start = session.info.get(SESSION_START_KEY)
    return round((time.perf_counter() - start) * 1000, 2) if start else 0.0


def _has_pending(session: AsyncSession) -> bool:
    """Whether ``session`` holds work that still needs committing.

    ``has_writes`` is stamped by the after_flush listener and survives the flush
    emptying ``session.new``/``.dirty``/``.deleted`` — the raw collections alone
    would report a flushed-but-uncommitted write as read-only.
    """
    return bool(
        session.info.get(SESSION_HAS_WRITES_KEY) or session.new or session.dirty or session.deleted
    )


def _settle(session: AsyncSession) -> None:
    """Mark the session finalized and clear the pending-write marker.

    Clearing matters: the marker is sticky, so without this a later finalize
    would try to re-commit a session whose work has already landed.
    """
    session.info[_FINALIZED_KEY] = True
    session.info.pop(SESSION_HAS_WRITES_KEY, None)


async def finalize_session(session: AsyncSession) -> None:
    """Commit ``session`` if it has pending writes, else roll it back.

    Safe to call more than once, and deliberately **re-armable** rather than
    one-shot. Work can still be done after the response has started — Starlette
    runs ``BackgroundTasks`` once the body is sent, and a ``StreamingResponse``
    writes its body after ``http.response.start`` — and both share this request's
    session. A one-shot claim would let the middleware's commit consume the
    session and then silently drop those later writes: they would flush and
    never commit. So each call commits whatever is pending *at that moment*, and
    ``get_db``'s exit code still runs afterwards to catch the rest.

    Read-only handlers exit via ``rollback`` — one round-trip cheaper than
    ``commit``, and it keeps read-only queries from showing up as writes in
    query logs / ``pg_stat_statements``. A repeat call with nothing new pending
    returns immediately rather than paying for a second rollback.

    On commit failure the session is rolled back before the error propagates,
    so the caller never has to reason about a half-finalized session.
    """
    if not _has_pending(session):
        if session.info.get(_FINALIZED_KEY):
            return
        _settle(session)
        await session.rollback()
        logger.debug(
            "db.session.read_only",
            extra={"operation": "read_only_rollback", "db_duration_ms": _elapsed_ms(session)},
        )
        return
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        # Settled either way: a failed commit must not be retried by the
        # fallback finalize in get_db's exit code.
        _settle(session)
    logger.info(
        "db.session.commit",
        extra={"operation": "commit", "db_duration_ms": _elapsed_ms(session)},
    )


async def rollback_session(session: AsyncSession) -> None:
    """Roll ``session`` back and drop its pending work. Idempotent."""
    if session.info.get(_FINALIZED_KEY) and not _has_pending(session):
        return
    _settle(session)
    await session.rollback()
    logger.warning(
        "db.session.rollback",
        extra={"operation": "rollback", "db_duration_ms": _elapsed_ms(session)},
    )


def register_request_session(scope: dict, session: AsyncSession) -> None:
    """Enlist ``session`` for commit-before-response, if the middleware is installed.

    A no-op when it isn't: ``get_db`` still commits in its own exit code, just
    later. That keeps the dependency usable on its own — in a WebSocket handler,
    a background task, or a test that never builds the middleware stack.
    """
    sessions = scope.get("state", {}).get(REQUEST_SESSIONS_KEY)
    if sessions is None:
        return
    sessions.append(session)


class CommitBeforeResponseMiddleware:
    """Finalize this request's DB sessions before the response is transmitted.

    Pure ASGI rather than ``BaseHTTPMiddleware`` because the hook point is the
    ``send`` channel, not the response object: intercepting
    ``http.response.start`` is what lets the commit land before any byte is
    written, and lets a commit failure still be turned into a 500.

    Install this **innermost** (add it first — Starlette's ``add_middleware`` is
    LIFO) so its wrapper is the first to see the response and the commit happens
    as early as possible.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        sessions: list[AsyncSession] = []
        scope.setdefault("state", {})[REQUEST_SESSIONS_KEY] = sessions
        aborted = False

        async def send_wrapper(message) -> None:
            nonlocal aborted
            if aborted:
                # The response we replaced is still streaming its body into a
                # channel we've already closed off. Drop it.
                return
            if message["type"] == "http.response.start" and sessions:
                try:
                    # A request normally has exactly one session (FastAPI caches
                    # the dependency). With several — Depends(get_db,
                    # use_cache=False) — a failure part-way leaves the earlier
                    # commits durable while the client sees a 500. There is no
                    # cross-session atomicity to recover here short of two-phase
                    # commit; the log line below is what makes it diagnosable.
                    for session in sessions:
                        await finalize_session(session)
                except Exception:
                    aborted = True
                    logger.exception(
                        "db.session.commit_failed", extra={"operation": "commit_failed"}
                    )
                    await _send_internal_error(send)
                    return
            await send(message)

        await self.app(scope, receive, send_wrapper)


async def _send_internal_error(send) -> None:
    """Replace the not-yet-sent response with a 500.

    Reachable only from ``http.response.start``, so nothing has been written
    and this cannot collide with a partially-sent response.
    """
    await send(
        {
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_INTERNAL_ERROR_BODY)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _INTERNAL_ERROR_BODY})
