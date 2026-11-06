# Load testing & profiling

Local load test for the backend using **locust** (traffic), **faker** (realistic
data volumes) and **memray** (allocation profiling). Run it against a
**throwaway database** so it never touches your dev data.

## Files

- `seed.py` — faker bulk data seed (users, role assignments, audit entries).
- `locustfile.py` — the `AuthedUser` browse scenario (weighted endpoint mix).
- Auth: `scripts/loadtest_seed.py` mints a forged session cookie
  (`SM_LOADTEST_COOKIE`) so locust skips the login flow and its rate limiter.
  It resolves host settings like the server: an explicit `SM_SECRET_KEY` wins,
  otherwise it uses the generated key stored in the database. Run the script
  with the same database and environment as the server.

## Prerequisites

Python deps installed (`make install` — `locust` and `faker` ship in the `dev`
group). A throwaway Postgres DB; with the shared dev-services stack up
(`make docker-up`):

```sh
docker exec dev-services-postgres-1 psql -U postgres -c "CREATE DATABASE smpy_loadtest"
export SM_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/smpy_loadtest
```

## 1. Migrate + seed realistic data

```sh
uv run --project host alembic -c host/alembic.ini upgrade heads
make loadtest-seed                       # 10k users + 100k audit rows (idempotent)
# or: make loadtest-seed SEED_ARGS="5000 50000"
docker exec dev-services-postgres-1 psql -U postgres -d smpy_loadtest -c "ANALYZE"
```

Seeding is idempotent — if the data is already present it is reused. Pass
`--force` (e.g. `uv run python tests/loadtest/seed.py 10000 100000 --force`) to
wipe and re-seed.

## 2. Run the app on a dedicated port

```sh
SM_MODULES_ENABLED='["Auth","FeatureFlags","Settings","FileStorage","Users","AuditLog","BackgroundTasks","Dashboard","Permissions"]' \
  uv run --project host uvicorn host.main:app --port 8000 --host 127.0.0.1
```

(`SM_MODULES_ENABLED` excludes `Keycloak` so only one auth provider is active —
otherwise the boot doctor fails with `SM020`.)

## 3. Load test (locust)

```sh
eval "$(uv run python scripts/loadtest_seed.py)"   # exports SM_LOADTEST_COOKIE
make loadtest                                       # headless against $(LOCUST_HOST)
# or override: make loadtest LOCUST_ARGS="-u 50 -r 10 -t 60s"
```

Each simulated user first loads `/dashboard/` as HTML. The scenario reads the
asset version and authenticated i18n catalog from the Inertia v3 JSON script,
then sends `X-Inertia-Version` and `X-SM-I18n: <locale>:full` on subsequent
Inertia visits, like a browser tab with a cached catalog. This initial HTML
request has its own stats row. Missing/invalid bootstrap data or an anonymous
catalog records a failure and stops that user. A 409 version conflict remains
a failure; restart the run after an asset deployment.

Older runs omitted both headers: the two Inertia tasks (20 weight points)
returned 409 instead of exercising their endpoints, and successful
page responses could include the full catalog (~71 KB). Their latency,
throughput and failure rates are not comparable with corrected runs.

**Size the pool before increasing concurrency.** At 300 users the default
`10 + 20` connection pool can be exhausted; queuing or pool timeouts then
dominate the result. Account for every worker's pool and Postgres's connection
limit, as described in [Deployment: pool sizing](../../docs/reference/deployment.md).
Record worker count, pool size/overflow, database size and asset version with
each result. Concurrency is not a reason to allocate one connection per user.

## 4. Profile allocations under load (memray)

`make loadtest-memray` seeds the auth cookie, starts uvicorn under memray,
drives it with locust, and renders a flamegraph. Run `make loadtest-seed` first
for realistic table sizes.

```sh
make loadtest-memray LOCUST_ARGS="-u 50 -r 10 -t 60s"
# open .memray/memray-flamegraph-loadtest.html
```

For CPU profiling, launch the app as a child of py-spy (Linux `ptrace_scope=1`
blocks attaching to a running process without root) and drive it with locust:

```sh
uvx py-spy record --format speedscope --subprocesses --duration 40 -o profile.json -- \
  uv run --project host uvicorn host.main:app --port 8000 --host 127.0.0.1
```

## Offline micro-benchmarks

`uv run python scripts/bench_loadtest_overheads.py` measures request helpers
without starting services. It reports median microseconds over five samples;
statement measurements build fresh query objects, as requests do. These
measurements demonstrate local CPU costs, not end-to-end throughput gains.

Local measurements on 2026-11-05 (same process setup before/after):

| Candidate | Before → after (µs) | Decision |
|---|---:|---|
| Validate path prefixes at tuple construction | 0.757 → 0.223 | Kept; all four gate callers validate once |
| Pre-encode and batch four static security headers (full wrapper) | 14.402 → 11.198 | Kept; CSP nonces, providers and HSTS still resolve as before |
| Construct flag DTO without validation | 4.693 → 4.633 | Dropped; ~1% was not a consistent gain across runs |
| Cache statement walk decision by SQLAlchemy key (fresh ORM query) | 45.925 → 48.822 | Dropped; key generation and lookup cost more than the walk |
| Skip session Vary normalization for a single token | 2.832 → 3.628 | Dropped; regresses the comma-separated Vary case (although a single Cookie token benefits) |

The installed Starlette session middleware already avoids re-signing unchanged
sessions. No session or query-filter code changed; tenancy and soft-delete
criteria remain untouched. The cache experiment timed a warmed lookup even
without the additional registry/policy invalidation a production cache needs.
