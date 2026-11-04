"""Write-side session bookkeeping: what counts as a write, and what a delete means.

Two decisions live here, both of which used to be made implicitly by the flush
listeners and both of which were wrong for statements the ORM never sees:

* **Did this session write anything?** ``get_db`` commits only a session that
  did. The flag was set from ``after_flush`` alone, so a request whose only
  write was ``session.execute(update(Model)...)`` was rolled back (GH #336).
* **Does ``session.delete()`` mean trash or purge?** It was unconditionally
  rewritten into a soft delete, leaving no way to purge at all (GH #335).
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ORMExecuteState, Session, SessionTransaction

from simple_module_db.mixins import SoftDeleteMixin

# Key on ``Session.info`` distinguishing read-only requests from write requests
# after flush has cleared ``session.new/.dirty/.deleted``.
SESSION_HAS_WRITES_KEY = "has_writes"
# Open transactions (root or savepoint) holding writes that have not committed.
_WRITE_TRANSACTIONS_KEY = "sm_db_write_transactions"
# Writes no open transaction owns: a commit the caller issued mid-request
# (fastapi-users commits inside ``update``/``create``) or a mark made with no
# transaction begun. Only ``clear_written`` or a full rollback drops it, so a
# later savepoint rollback cannot discard the on-commit work of durable writes.
_UNTRACKED_WRITES_KEY = "sm_db_untracked_writes"
# Class marker for the transaction listeners; see ``attach_write_listeners``.
_WRITE_LISTENERS_ATTACHED = "_sm_write_listeners_attached"

# Key on ``Session.info`` holding ``id()`` of instances the caller asked to
# hard-delete, consumed by the before_flush soft-delete rewrite.
_HARD_DELETE_KEY = "_hard_delete"


def mark_written(session: Session | AsyncSession) -> None:
    """Flag ``session`` as having performed write work.

    ``get_db`` commits only a session carrying this flag. It is stamped
    automatically for ORM flushes and for DML executed through the session, so
    the only caller that needs this is one issuing a write the ORM never sees —
    ``session.execute(text("UPDATE ..."))``, or DML against a bare ``Table``.
    Without it that write is rolled back at request end, silently (GH #336).

    Accepts either an ``AsyncSession`` or the underlying sync ``Session``.
    The mark belongs to the innermost open transaction: releasing a savepoint
    hands it to the parent, rolling one back discards it. It never begins a
    transaction; with none open the flag is simply set.
    """
    sync_session = session.sync_session if isinstance(session, AsyncSession) else session
    if not _class_wired(type(sync_session)) and not event.contains(
        sync_session, "after_commit", _merge_written_transaction
    ):
        # A session class the framework never wired (a bare test session).
        event.listen(sync_session, "after_commit", _merge_written_transaction)
        event.listen(sync_session, "after_soft_rollback", _discard_written_transaction)
    info = sync_session.info
    transaction = sync_session.get_nested_transaction() or sync_session.get_transaction()
    if transaction is None:
        info[_UNTRACKED_WRITES_KEY] = True
    else:
        info.setdefault(_WRITE_TRANSACTIONS_KEY, set()).add(transaction)
    info[SESSION_HAS_WRITES_KEY] = True


def clear_written(session: Session | AsyncSession) -> None:
    """Forget every write mark: the session's work was finalized."""
    for key in (SESSION_HAS_WRITES_KEY, _WRITE_TRANSACTIONS_KEY, _UNTRACKED_WRITES_KEY):
        session.info.pop(key, None)


def attach_write_listeners(session_class: type[Session]) -> None:
    """Track write marks across commits and savepoint rollbacks; idempotent.

    Registered once per session class (``attach_session_listeners``); a
    subclass inherits class-level session listeners, so it is skipped.
    """
    if _class_wired(session_class):
        return
    event.listen(session_class, "after_commit", _merge_written_transaction)
    event.listen(session_class, "after_soft_rollback", _discard_written_transaction)
    setattr(session_class, _WRITE_LISTENERS_ATTACHED, True)


def _class_wired(session_class: type) -> bool:
    return any(base.__dict__.get(_WRITE_LISTENERS_ATTACHED) for base in session_class.__mro__)


def _merge_written_transaction(session: Session) -> None:
    # ``after_commit`` fires for the root and for released savepoints, while
    # the committing transaction is still the current one.
    transaction = session.get_nested_transaction() or session.get_transaction()
    if transaction is None:
        return
    written: set[SessionTransaction] = session.info.get(_WRITE_TRANSACTIONS_KEY, set())
    if transaction not in written:
        return
    written.remove(transaction)
    if transaction.parent is None:
        # Durable now, but its on-commit work still waits for finalization.
        session.info[_UNTRACKED_WRITES_KEY] = True
    else:
        written.add(transaction.parent)


def _discard_written_transaction(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:
        clear_written(session)
        return
    written: set[SessionTransaction] = session.info.get(_WRITE_TRANSACTIONS_KEY, set())
    if transaction not in written:
        return
    written.remove(transaction)
    if not written and not session.info.get(_UNTRACKED_WRITES_KEY):
        session.info.pop(SESSION_HAS_WRITES_KEY, None)


def _mark_session_written(session: Session, flush_context: object) -> None:
    """``after_flush`` hook: flag the session as having performed write work.

    Checking ``session.new/.dirty/.deleted`` directly after a flush is useless
    — flush empties those sets — so we stash a tag on ``session.info`` that
    survives the rest of the request.
    """
    mark_written(session)


def _mark_dml_written(execute_state: ORMExecuteState) -> None:
    """``do_orm_execute`` hook: flag Core DML as write work.

    ``await session.execute(update(Model)...)`` never runs the unit of work, so
    ``after_flush`` never fires and the statement — which *did* execute — was
    rolled back at request end with no error (GH #336). The canonical
    optimistic-concurrency write and every bulk update/purge has that shape.

    Matched on ``is_insert``/``is_update``/``is_delete`` rather than
    ``not is_select`` on purpose: a ``text("SELECT ...")`` statement reports
    ``False`` for all four, and marking it written would make every raw-SQL read
    pay for a commit.
    """
    if execute_state.is_insert or execute_state.is_update or execute_state.is_delete:
        mark_written(execute_state.session)


async def hard_delete(session: AsyncSession, instance: object) -> None:
    """Delete ``instance`` for real, bypassing the soft-delete rewrite.

    ``session.delete()`` on a :class:`~simple_module_db.mixins.SoftDeleteMixin`
    row is rewritten into a soft delete, which left a module with a trash screen
    no supported way to express a purge (GH #335). Note that a row that is
    *already* soft-deleted hard-deletes through plain ``session.delete()`` — the
    second delete purges — so this helper is only needed to purge a live row in
    one step.

    The delete is flushed immediately, because the marker is consumed by the
    next flush and would otherwise apply to whatever that flush happens to hold.
    """
    session.info.setdefault(_HARD_DELETE_KEY, set()).add(id(instance))
    await session.delete(instance)
    await session.flush()


def _is_purge(obj: SoftDeleteMixin, hard_delete_ids: frozenset[int] | set[int]) -> bool:
    """Whether this delete should go through to the DB instead of being rewritten.

    Two ways to purge (GH #335):

    * the caller went through :func:`hard_delete`, or
    * the row is *already* soft-deleted in the database, so re-stamping it would
      be a no-op — deleting from the trash is what a purge means.

    The second test reads the **loaded** value, not the current one: a caller
    that sets ``is_deleted = True`` and deletes in the same flush means "trash
    this", and must not have the row torn out from under them.
    """
    if id(obj) in hard_delete_ids:
        return True
    history = sa_inspect(obj).attrs.is_deleted.history
    if history.deleted:
        return bool(history.deleted[0])
    return bool(obj.is_deleted)
