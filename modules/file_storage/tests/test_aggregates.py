"""The bucket totals: one scan for three answers, memoised, dropped on write.

Byte usage and both facet lists used to be three separate unfiltered scans of
``file_storage_stored_file``, recomputed on every browse render including the
ones that only changed ``?page=`` — so the cost of the screen grew with the
bucket rather than with the page (GH #299). These cover the replacement: a
single grouped query the three answers are folded out of, and a cache that a
commit touching a file row drops.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from file_storage import constants
from file_storage.aggregates import AggregateCache, compute, register_invalidation
from file_storage.models import StoredFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

TABLE = constants.TABLE_STORED_FILE
ALICE = "11111111-1111-1111-1111-111111111111"
BOB = "22222222-2222-2222-2222-222222222222"


async def _seed(db: AsyncSession, *rows: tuple[str, str | None, int]) -> list[StoredFile]:
    """Insert ``(content_type, created_by, size_bytes)`` rows."""
    made = []
    for content_type, owner, size in rows:
        row = StoredFile(
            key=f"2026/01/01/{uuid.uuid4().hex}",
            filename=f"{uuid.uuid4().hex}.bin",
            content_type=content_type,
            size_bytes=size,
            backend=constants.BackendId.FILESYSTEM,
            checksum_sha256="0" * 64,
            created_by=owner,
        )
        db.add(row)
        made.append(row)
    await db.flush()
    return made


class TestOneQueryAnswersAllThree:
    """The shape assertion the issue asks for: one scan, not three."""

    async def test_a_single_statement_produces_every_total(
        self, db_session: AsyncSession, engine, record_statements
    ):
        await _seed(db_session, ("text/plain", ALICE, 5), ("image/png", BOB, 3))

        with record_statements(engine) as seen:
            await compute(db_session)

        against_table = [s for s in seen if TABLE in s]
        assert len(against_table) == 1, against_table
        # And it is the grouped one, not three scans that happen to have been
        # coalesced by a driver.
        assert "GROUP BY" in against_table[0].upper()

    async def test_folds_counts_and_bytes_out_of_the_same_grid(self, db_session: AsyncSession):
        await _seed(
            db_session,
            ("text/plain", ALICE, 5),
            ("text/plain", BOB, 3),
            ("image/png", ALICE, 10),
        )

        totals = await compute(db_session)

        assert {f.value: f.count for f in totals.content_types} == {"text/plain": 2, "image/png": 1}
        assert {f.value: f.count for f in totals.uploaders} == {ALICE: 2, BOB: 1}
        assert totals.used_bytes == 18

    async def test_facets_are_ordered_by_value(self, db_session: AsyncSession):
        """The dropdowns used to get an ``ORDER BY``; the fold must keep it."""
        await _seed(db_session, ("text/plain", BOB, 1), ("image/png", ALICE, 1))

        totals = await compute(db_session)

        assert [f.value for f in totals.content_types] == ["image/png", "text/plain"]
        assert [f.value for f in totals.uploaders] == [ALICE, BOB]

    async def test_rows_with_no_uploader_count_but_are_not_offered(self, db_session: AsyncSession):
        """``created_by=None`` already means "every uploader" to the listing
        query, so a "no uploader" option could not be round-tripped — but the
        bytes and the type facet are still real."""
        await _seed(db_session, ("text/plain", None, 7))

        totals = await compute(db_session)

        assert totals.uploaders == ()
        assert {f.value: f.count for f in totals.content_types} == {"text/plain": 1}
        assert totals.used_bytes == 7

    async def test_deleted_rows_stop_counting(self, db_session: AsyncSession):
        keep, gone = await _seed(db_session, ("text/plain", ALICE, 5), ("image/png", ALICE, 3))
        gone.is_deleted = True
        gone.deleted_at = datetime.now(UTC)
        await db_session.flush()

        totals = await compute(db_session)

        assert totals.used_bytes == 5
        assert [f.value for f in totals.content_types] == ["text/plain"]
        assert {f.count for f in totals.uploaders} == {1}
        assert keep.is_deleted is False

    async def test_an_empty_bucket_reports_zero_rather_than_none(self, db_session: AsyncSession):
        totals = await compute(db_session)

        assert totals == type(totals)(content_types=(), uploaders=(), used_bytes=0)


class TestCache:
    async def test_a_second_read_does_not_touch_the_database(
        self, db_session: AsyncSession, engine, record_statements
    ):
        await _seed(db_session, ("text/plain", ALICE, 5))
        cache = AggregateCache()
        await cache.get(db_session)

        with record_statements(engine) as seen:
            again = await cache.get(db_session)

        assert [s for s in seen if TABLE in s] == []
        assert again.used_bytes == 5

    async def test_invalidating_forces_a_re_read(self, db_session: AsyncSession):
        await _seed(db_session, ("text/plain", ALICE, 5))
        cache = AggregateCache()
        await cache.get(db_session)
        await _seed(db_session, ("text/plain", ALICE, 4))

        cache.invalidate()

        assert (await cache.get(db_session)).used_bytes == 9

    async def test_an_expired_entry_is_not_served(self, db_session: AsyncSession):
        """The TTL is the ceiling on staleness for a write another worker made,
        which no in-process invalidation can see."""
        await _seed(db_session, ("text/plain", ALICE, 5))
        cache = AggregateCache(ttl_seconds=0)
        await cache.get(db_session)
        await _seed(db_session, ("text/plain", ALICE, 4))

        assert cache.peek() is None
        assert (await cache.get(db_session)).used_bytes == 9


class TestInvalidationWiring:
    """Invalidation hangs off the commit, so it must fire for *any* writer."""

    async def test_a_commit_that_wrote_a_file_drops_the_cache(self, db_session, db_state):
        cache = AggregateCache()
        register_invalidation(db_state, cache)
        await cache.get(db_session)

        async with db_state.session_factory() as other:
            await _seed(other, ("text/plain", ALICE, 4))
            await other.commit()

        assert cache.peek() is None

    async def test_a_session_that_wrote_nothing_leaves_the_cache_alone(self, db_session, db_state):
        """Otherwise every request in the app would clear it and the cache
        would only ever be paid for."""
        cache = AggregateCache()
        register_invalidation(db_state, cache)
        await cache.get(db_session)

        async with db_state.session_factory() as other:
            await other.execute(select(StoredFile))
            await other.commit()

        assert cache.peek() is not None

    async def test_each_app_gets_its_own_wiring(self, db_session, db_state):
        """A second app in the same process must not be left with a cache
        nothing invalidates — the failure mode of an ``id()``-keyed guard,
        since a torn-down app's session class can have its address reused."""
        first, second = AggregateCache(), AggregateCache()
        register_invalidation(db_state, first)
        register_invalidation(db_state, second)
        await first.get(db_session)
        await second.get(db_session)

        async with db_state.session_factory() as other:
            await _seed(other, ("text/plain", ALICE, 4))
            await other.commit()

        assert first.peek() is None
        assert second.peek() is None
