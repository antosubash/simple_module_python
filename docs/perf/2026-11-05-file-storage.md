# File-storage performance fixes, 2026-11-05

Local review against `4920a13a`: synchronous server-upload spool I/O, per-part
S3 clients, and a missing ordered tenant browse index.

## Local measurements

No S3, HTTP server, browser, or PostgreSQL service was used. These measurements
are evidence for the local changes, not production latency predictions.

### Upload loop lag

Two concurrent uploads (32 MiB and 64 MiB), 1 MiB source chunks, real temporary
files with the existing 10 MiB spool limit, and the existing `S3Wire` fake.
The wire consumed file bodies in executor threads, like aiohttp's file payload,
without simulating network latency. A 1 ms asyncio timer sampled scheduling
lag. Known sizes used the actual length; unknown sizes used zero. Each row is
one before/after run, so small sample sizes and filesystem cache effects apply.

| Threshold | Size known | Loop lag p99 before → after | Elapsed before → after | Client opens before → after |
| --- | --- | --- | --- | --- |
| 16 MiB (force multipart) | yes | 30.617 → 9.282 ms | 0.235 → 0.499 s | 10 → 2 |
| 16 MiB (force multipart) | no | 60.710 → 0.953 ms | 0.290 → 1.784 s | 10 → 2 |
| 64 MiB (default; single PUT) | yes | 38.319 → 9.581 ms | 0.249 → 0.504 s | 2 → 2 |
| 64 MiB (default; single PUT) | no | 38.173 → 6.892 ms | 0.280 → 0.432 s | 2 → 2 |

Offloading improves responsiveness but adds executor overhead. This fake-only
run cannot establish end-to-end throughput or connection reuse at the network
level. In particular, unknown-size multipart uploads replay the prefix in
64 KiB chunks, causing more executor round trips.

This sandbox stalled on asyncio executor-completion wakeups despite idle
worker threads. Tests and measurements used a temporary pytest fixture with a
1 ms periodic asyncio sleep to keep the selector waking. This workaround was
not added to production or repository test configuration. Initial stalled runs
were interrupted; the final targeted run passed all 36 tests.

`/health` p99 during real S3 uploads remains unmeasured under the no-server
constraint. SDK-internal signing/checksum work was not profiled by this fake.

### Browse query

`test_file_storage_browse_index.py` loads 100,000 rows for one live tenant into
SQLite and checks the first 25 IDs, before and after migration `f6c2d4e8b109`.
Ten executions averaged **38.455 → 0.076 ms**. Before the change SQLite used a
temporary B-tree for ordering; afterward the ordered tenant index served the
page without a sort. Both model metadata and the upgrade/downgrade are tested.

The test uses SQLite as a local proxy. A PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)`
on 100k+ representative tenant files remains necessary to establish that
platform's plan and timings. The index targets the default live-file order;
counts, alternate sort orders and arbitrary filters may still scan or sort.

## Validation

New regressions cover threaded spool writes, reads, seeks, truncation and close,
known and unknown sizes, one client per multipart upload, cancellation during
an in-flight write (including repeated cancellation), model index selection,
and migration upgrade/downgrade. Existing server-put tests cover memory bounds,
thresholds, size mismatch, part-count limits and abort on stream, part and
completion failure. Migration graph checks pin the new shared trunk head. Ruff formatting/checks,
targeted `ty` checks on the changed production files, and `git diff --check`
passed. `make doctor` was attempted against in-memory SQLite but stalled without
diagnostic output and was interrupted; its result is unavailable. Full suites
were excluded by the task constraints.
