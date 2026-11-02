"""Post-commit callbacks for framework-managed database sessions."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

type OnCommitCallback = Callable[[], Awaitable[None] | None]
type _CallbackEntry = tuple[set[SessionTransaction], OnCommitCallback]

_CALLBACKS_KEY = "sm_db_on_commit_callbacks"
logger = logging.getLogger("simple_module.db")


def register_on_commit(session: AsyncSession, callback: OnCommitCallback) -> None:
    """Queue ``callback`` for this session's next successful finalization."""
    if not callable(callback):
        raise TypeError("on_commit callback must be callable")
    sync_session = session.sync_session
    if not event.contains(sync_session, "after_soft_rollback", _discard_rolled_back_callbacks):
        event.listen(sync_session, "after_soft_rollback", _discard_rolled_back_callbacks)
    savepoints: set[SessionTransaction] = set()
    transaction = sync_session.get_nested_transaction()
    # Keep ancestors too: a released child still belongs to its parent's rollback.
    while transaction is not None:
        if transaction.nested:
            savepoints.add(transaction)
        transaction = transaction.parent
    callbacks = session.info.setdefault(_CALLBACKS_KEY, [])
    callbacks.append((savepoints, callback))


def _discard_rolled_back_callbacks(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:
        session.info.pop(_CALLBACKS_KEY, None)
    elif transaction.nested and _CALLBACKS_KEY in session.info:
        session.info[_CALLBACKS_KEY] = [
            entry for entry in session.info[_CALLBACKS_KEY] if transaction not in entry[0]
        ]


def discard_on_commit_callbacks(session: AsyncSession) -> None:
    """Discard callbacks belonging to a transaction that did not commit."""
    session.info.pop(_CALLBACKS_KEY, None)


async def run_on_commit_callbacks(session: AsyncSession) -> None:
    """Run and remove queued callbacks after a successful commit.

    The transaction is already durable, so callback failures are logged and do
    not turn a successful database mutation into a misleading failed response.
    Remaining callbacks still run.
    """
    callbacks: list[_CallbackEntry] = session.info.pop(_CALLBACKS_KEY, [])
    for _, callback in callbacks:
        try:
            result = callback()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception(
                "db.session.on_commit_failed",
                extra={"operation": "on_commit_failed"},
            )
