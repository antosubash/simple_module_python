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

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ORMExecuteState, Session

from simple_module_db.mixins import SoftDeleteMixin

# Key on ``Session.info`` distinguishing read-only requests from write requests
# after flush has cleared ``session.new/.dirty/.deleted``.
SESSION_HAS_WRITES_KEY = "has_writes"

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
    """
    session.info[SESSION_HAS_WRITES_KEY] = True


def _mark_session_written(session: Session, flush_context: object) -> None:
    """``after_flush`` hook: flag the session as having performed write work.

    Checking ``session.new/.dirty/.deleted`` directly after a flush is useless
    — flush empties those sets — so we stash a tag on ``session.info`` that
    survives the rest of the request.
    """
    session.info[SESSION_HAS_WRITES_KEY] = True


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
        execute_state.session.info[SESSION_HAS_WRITES_KEY] = True


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
