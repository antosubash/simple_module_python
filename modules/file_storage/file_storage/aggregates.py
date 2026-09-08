"""Bucket-wide numbers for the browse screen — one scan, cached, dropped on write.

The header's "used" figure and both filter dropdowns describe *the bucket*, not
the page: a facet list that hid its own alternatives would be a dead end, and a
usage figure that shrank when someone typed in the search box would describe
nothing. That is right, and it used to cost three separate full-table scans on
every render — including the renders that only changed ``?page=``.

Two things fix that, and this module holds both:

* **One scan instead of three.** ``GROUP BY content_type, created_by`` with a
  count and a byte sum yields a small grid (distinct types by distinct
  uploaders) from which all three answers are folded in Python. Not
  ``GROUPING SETS``: SQLite has no support for it, and the grid is already
  bounded by cardinality the filter dropdowns have to be able to render anyway.
* **A short TTL cache with write-driven invalidation.** These numbers tolerate
  being seconds stale — they describe a bucket, not a record — but they must
  not be stale *after your own upload*, so the cache is dropped by any commit
  that wrote a ``StoredFile``. Invalidating off the DB write rather than off
  ``FileUploaded``/``FileDeleted`` is deliberate: it also catches the writes
  that publish nothing (a seed script, a migration back-fill, a fix-up in the
  shell) and it fires *after* the commit, so a concurrent reader can never
  re-cache the pre-commit numbers for a whole TTL.

The cache is per-app (held on ``FileStorageServices``), not per-process: a
process running two apps — the test suite does — must not serve one app's
totals from the other's database.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from file_storage.models import StoredFile

if TYPE_CHECKING:
    from simple_module_db.session import DatabaseState

AGGREGATE_TTL_SECONDS: float = 30.0
"""How long a computed set of bucket totals is reused without re-scanning.

A ceiling on staleness for the one case invalidation cannot cover — another
worker process's write. Short enough that nobody reasons from a number that
old; long enough to collapse a burst of pagination into a single scan.
"""

_WROTE_FILES_KEY = "file_storage_wrote_files"
"""``Session.info`` flag set at flush and read at commit.

Stamped in ``before_flush`` because that is the last point at which
``session.new``/``.dirty``/``.deleted`` still name the objects being written;
read in ``after_commit`` so the cache is dropped only once the new rows are
actually visible to the next reader.
"""


@dataclass(frozen=True, slots=True)
class Facet:
    """One option in a filter dropdown, with how many rows carry it."""

    value: str
    count: int

    def as_dict(self) -> dict:
        """Wire shape consumed by ``Browse.tsx`` and the facet tests."""
        return {"value": self.value, "count": self.count}


@dataclass(frozen=True, slots=True)
class StorageAggregates:
    """Everything the browse header and its dropdowns need about the bucket.

    Frozen and tuple-backed because instances are shared between requests once
    cached: a caller that sorted the facet list in place would be editing the
    next reader's copy.
    """

    content_types: tuple[Facet, ...]
    uploaders: tuple[Facet, ...]
    used_bytes: int


async def compute(db: AsyncSession) -> StorageAggregates:
    """Fold one grouped scan into the three answers the screen asks for.

    Deleted rows are excluded by the soft-delete loader criteria, which attach
    per mapper *named in the statement* — every column here is a mapped one, so
    a deleted file stops counting against the bucket the moment it goes.

    Uploaders with no ``created_by`` (rows predating authenticated uploads) are
    counted into the byte total and the type facets but not offered as an
    uploader option: ``created_by=None`` already means "every uploader" to the
    listing query, so a "no uploader" choice could not be round-tripped through
    the query string honestly.
    """
    grid = (
        await db.execute(
            select(
                StoredFile.content_type,
                StoredFile.created_by,
                func.count(StoredFile.id),
                func.coalesce(func.sum(StoredFile.size_bytes), 0),
            ).group_by(StoredFile.content_type, StoredFile.created_by)
        )
    ).all()

    by_type: dict[str, int] = {}
    by_uploader: dict[str, int] = {}
    total = 0
    for content_type, created_by, count, size in grid:
        rows = int(count)
        by_type[str(content_type)] = by_type.get(str(content_type), 0) + rows
        if created_by is not None:
            by_uploader[str(created_by)] = by_uploader.get(str(created_by), 0) + rows
        total += int(size or 0)

    return StorageAggregates(
        content_types=_facets(by_type),
        uploaders=_facets(by_uploader),
        used_bytes=total,
    )


def _facets(counts: dict[str, int]) -> tuple[Facet, ...]:
    """Sorted by value, matching the ``ORDER BY`` the dropdowns used to get."""
    return tuple(Facet(value=value, count=count) for value, count in sorted(counts.items()))


@dataclass
class AggregateCache:
    """One slot's worth of memoised totals, with an expiry and a manual drop.

    Deliberately not ``cachetools``: a single entry with one expiry is two
    fields, and ``file_storage`` would otherwise grow a dependency to hold them.
    """

    ttl_seconds: float = AGGREGATE_TTL_SECONDS
    _value: StorageAggregates | None = field(default=None, init=False, repr=False)
    _expires_at: float = field(default=0.0, init=False, repr=False)
    _wired: bool = field(default=False, init=False, repr=False)
    """Whether :func:`register_invalidation` has already attached this cache."""

    def invalidate(self) -> None:
        """Forget the cached totals — the next read re-scans."""
        self._value = None
        self._expires_at = 0.0

    def peek(self) -> StorageAggregates | None:
        """The cached totals if still fresh, else ``None``. No DB access."""
        if self._value is None or time.monotonic() >= self._expires_at:
            return None
        return self._value

    async def get(self, db: AsyncSession) -> StorageAggregates:
        """Cached totals, computing them on a miss."""
        cached = self.peek()
        if cached is not None:
            return cached
        value = await compute(db)
        self._value = value
        self._expires_at = time.monotonic() + self.ttl_seconds
        return value


def _mark_stored_file_writes(session, flush_context, instances) -> None:
    """Flag the session if this flush touches a stored file."""
    if session.info.get(_WROTE_FILES_KEY):
        return
    for obj in (*session.new, *session.dirty, *session.deleted):
        if isinstance(obj, StoredFile):
            session.info[_WROTE_FILES_KEY] = True
            return


def _drop_on_commit(cache: AggregateCache, session) -> None:
    """Drop the cached totals once a file-writing session has committed.

    The flag is read, not consumed: a session can commit more than once — the
    commit-before-response middleware is deliberately re-armable — and a
    listener that ate the flag would leave a second cache on the same session
    class, or a second commit, with nothing to act on. Re-dropping an already
    dropped cache costs nothing; missing a drop serves a stale number.
    """
    if session.info.get(_WROTE_FILES_KEY):
        cache.invalidate()


def register_invalidation(db_state: DatabaseState, cache: AggregateCache) -> None:
    """Wire ``cache`` to this app's sessions. Safe to call more than once.

    ``sync_session_class`` is a per-``DatabaseState`` subclass, so the listeners
    only ever see sessions belonging to this app's engine — and one cache is
    wired to exactly one of them, which is what makes the flag a sufficient
    guard. Not ``event.contains``: its key is ``id(target)``, and a session
    class from a torn-down app can be collected and its address reused by the
    next one, which reads back as "already registered" and silently leaves the
    new app's cache with nothing to invalidate it.
    """
    if cache._wired:
        return
    cache._wired = True
    session_class = db_state.sync_session_class
    event.listen(session_class, "before_flush", _mark_stored_file_writes)
    event.listen(session_class, "after_commit", partial(_drop_on_commit, cache))
