"""Keep a durable handler from committing ``ctx.db`` itself (GH #459).

A handler's database effects land exactly once because they commit in the
same transaction as the fenced ``delivered`` mark: if the claim was lost the
whole session rolls back. A handler — or library code it calls, such as a
helper that ends with ``await session.commit()`` or an ``async with
session.begin():`` block — that commits ``ctx.db`` on its own makes its writes
durable *before* the fence is checked, so a later failure or a lost lease runs
them again.

:func:`handler_guard` refuses that commit: while the handler runs, a
``before_commit`` listener on the session raises :class:`HandlerCommitError`
before anything reaches the database. Releasing a savepoint
(``begin_nested()``) is not a commit and is allowed — the race-safe insert
idiom relies on it — while a root commit with a savepoint open is still
refused. Committing through the session's ``Connection``
(``(await ctx.db.connection()).commit()``, as Connection-oriented libraries
do) never reaches ``Session.before_commit``, so every connection the session
begins on while the handler runs is marked, and an engine-level ``commit``
listener refuses it too. A handler that catches and swallows the error still
fails its attempt — the guard remembers the refused commit and raises again
when the handler returns — so the whole attempt rolls back and is retried like
any other failure.

The guard covers ``ctx.db`` only. Work a handler does elsewhere — another
session (even one on ``ctx.db.bind``), a raw DBAPI ``COMMIT``, an HTTP call, an
email — is at-least-once and must be idempotent.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

_ACTIVE_KEY = "background_tasks_outbox_handler_running"
_REFUSED_KEY = "background_tasks_outbox_commit_refused"
_HOOKED_KEY = "background_tasks_outbox_guard_hooked"
# On ``Connection.info`` (the pooled DBAPI connection's): the guarded session.
_CONN_KEY = "background_tasks_outbox_guarded_session"
# On the session: the connections marked while the handler runs.
_CONNS_KEY = "background_tasks_outbox_guarded_connections"

MESSAGE = (
    "Durable handlers must not commit ctx.db: the outbox commits it together with "
    "marking the delivery done, which is what makes its effects land exactly once. "
    "Flush instead (await ctx.db.flush()) if you need database-assigned values."
)


class HandlerCommitError(RuntimeError):
    """A durable handler (or code it called) tried to commit ``ctx.db``."""


def _before_commit(session: Session) -> None:
    if not session.info.get(_ACTIVE_KEY):
        return
    # Fires for a SAVEPOINT release too; that makes nothing durable. A root
    # commit issued while a savepoint is open still reaches this hook once the
    # savepoint is released, with no nested transaction left, and is refused.
    if session.in_nested_transaction():
        return
    session.info[_REFUSED_KEY] = True
    raise HandlerCommitError(MESSAGE)


def _on_connection_commit(conn: Connection) -> None:
    session = conn.info.get(_CONN_KEY)
    if session is not None and session.info.get(_ACTIVE_KEY):
        session.info[_REFUSED_KEY] = True
        raise HandlerCommitError(MESSAGE)


def _mark(session: Session, conn: Connection) -> None:
    engine = conn.engine
    if not event.contains(engine, "commit", _on_connection_commit):
        event.listen(engine, "commit", _on_connection_commit)
    conn.info[_CONN_KEY] = session
    session.info.setdefault(_CONNS_KEY, []).append(conn)


def _after_begin(session: Session, transaction: Any, conn: Connection) -> None:
    if session.info.get(_ACTIVE_KEY):
        _mark(session, conn)


@contextmanager
def handler_guard(session: Any) -> Generator[None]:
    """Refuse any commit of *session* (an ``AsyncSession``) inside the block."""
    sync = session.sync_session
    if not sync.info.get(_HOOKED_KEY):
        event.listen(sync, "before_commit", _before_commit)
        event.listen(sync, "after_begin", _after_begin)
        sync.info[_HOOKED_KEY] = True
    sync.info[_ACTIVE_KEY] = True
    sync.info.pop(_REFUSED_KEY, None)
    try:
        yield
    finally:
        sync.info.pop(_ACTIVE_KEY, None)
        # Unmark, so the delivery commit — and whoever checks the pooled
        # connection out next — is not refused.
        for conn in sync.info.pop(_CONNS_KEY, []):
            conn.info.pop(_CONN_KEY, None)
    if sync.info.pop(_REFUSED_KEY, False):
        raise HandlerCommitError(MESSAGE)


__all__ = ["HandlerCommitError", "handler_guard"]
