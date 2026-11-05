# Background task read performance

Measured on 2026-11-05 for the local review of `main@4920a13a`.

## Method

Local SQLite 3.53.1, Python 3.12, synchronous SQLAlchemy sessions against a
throwaway file database. No app server, worker, browser or external service.
This measures SQL execution, ORM materialization and DTO validation, excluding
HTTP handling and network latency. These are SQLite results, not PostgreSQL
estimates.

The list dataset contains 100,000 successful executions, each with one integer
argument, one integer keyword argument, a JSON result containing 1,000 ASCII
characters, and a 180-character traceback. Timestamps increase by one second;
every twentieth timestamp is null. Existing model indexes remain present.
Baseline runs omit the new ordering index; revised runs include it.

The baseline list runs the original full-entity select with `count(*) OVER ()`,
`ORDER BY queued_at DESC NULLS LAST` and `LIMIT 20`. The revised list runs an
exact `count(*)` followed by a DTO-column-only select with
`ORDER BY queued_at IS NULL, queued_at DESC LIMIT 20`. Both validate all returned
list DTOs. Assertions check equal first-page IDs, 20 rows and a 100,000 total.
Timings are medians of five runs after one warmup, with a fresh session each run.

For polling, one row's result is replaced with `{"data": "x" * 1_000_000}`
(1,000,012 bytes encoded as JSON). Both selects use the endpoint's
`celery_task_id` predicate, descending queued timestamp and `LIMIT 1`. The revised
select loads DTO fields plus authorization fields, with other columns set to
raise on deferred access. An assertion checks identical status DTOs. Timings
use five runs after warmup; memory uses the median peak from 15 fresh
`tracemalloc` runs, collecting garbage before each run. Memory measures Python
allocations during the complete read and DTO conversion, not native SQLite
buffers or HTTP response size.

## Results

| Measurement | Before | After |
|---|---:|---:|
| First list page, including exact total | 1,418.00 ms | 3.54 ms |
| Poll with 1 MB result | 3.10 ms | 0.48 ms |
| Peak traced Python memory per poll | 2,024,547 bytes | 23,428 bytes |
| Selected raw values per poll, UTF-8 bytes | 1,000,309 | 49 |

The raw-value byte sum encodes each non-null SQLite driver value as text and
adds its byte length. It excludes driver/protocol framing and is not a wire-byte
measurement. The status response itself is unchanged. The entire 1,000,012-byte
JSON result, as well as arguments and traceback, is excluded from the new poll.

`EXPLAIN QUERY PLAN` before:

```text
CO-ROUTINE (subquery-2)
SCAN background_tasks_task_execution
SCAN (subquery-2)
USE TEMP B-TREE FOR ORDER BY
```

After, count:

```text
SCAN background_tasks_task_execution USING COVERING INDEX ix_background_tasks_task_execution_queued_order
```

After, page:

```text
SCAN background_tasks_task_execution USING INDEX ix_background_tasks_task_execution_queued_order
```

## Limits and PostgreSQL follow-up

PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` was not run: this task forbids starting
servers and no PostgreSQL measurement connection was provided. The migration's
PostgreSQL DDL is checked offline; execution and planner behavior there remain
unverified. No million-row run was made. SQLite's large improvement includes
avoiding its wide-row window spool and sort; do not extrapolate its ratio to
PostgreSQL.

On a disposable PostgreSQL database with 100,000–1,000,000 representative
executions, compare the original full-row window query with the separate count
and projected page, using `EXPLAIN (ANALYZE, BUFFERS)` for each. The page order
must be `queued_at IS NULL, queued_at DESC` to match the portable expression
index in migration `c5d8e2f1a903`. Test filtered and deep pages too. Exact counts
still visit matching history, and offset pagination still visits skipped index
entries. Count and page are separate statements, so concurrent writes can make
them reflect different snapshots under PostgreSQL's default READ COMMITTED.
