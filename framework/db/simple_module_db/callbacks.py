"""Post-commit callbacks for framework-managed database sessions."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

type OnCommitCallback = Callable[[], Awaitable[None] | None]

_CALLBACKS_KEY = "sm_db_on_commit_callbacks"
logger = logging.getLogger("simple_module.db")


def register_on_commit(session: AsyncSession, callback: OnCommitCallback) -> None:
    """Queue ``callback`` for this session's next successful finalization."""
    if not callable(callback):
        raise TypeError("on_commit callback must be callable")
    callbacks = session.info.setdefault(_CALLBACKS_KEY, [])
    callbacks.append(callback)


def discard_on_commit_callbacks(session: AsyncSession) -> None:
    """Discard callbacks belonging to a transaction that did not commit."""
    session.info.pop(_CALLBACKS_KEY, None)


async def run_on_commit_callbacks(session: AsyncSession) -> None:
    """Run and remove queued callbacks after a successful commit.

    The transaction is already durable, so callback failures are logged and do
    not turn a successful database mutation into a misleading failed response.
    Remaining callbacks still run.
    """
    callbacks: list[OnCommitCallback] = session.info.pop(_CALLBACKS_KEY, [])
    for callback in callbacks:
        try:
            result = callback()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception(
                "db.session.on_commit_failed",
                extra={"operation": "on_commit_failed"},
            )
