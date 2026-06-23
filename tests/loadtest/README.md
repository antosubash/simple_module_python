# Load testing & profiling

Local load test for the backend using **locust** (traffic), **faker** (realistic
data volumes) and **memray** (allocation profiling). Run it against a
**throwaway database** so it never touches your dev data.

## Files

- `seed.py` — faker bulk data seed (users, role assignments, audit entries).
- `locustfile.py` — the `AuthedUser` browse scenario (weighted endpoint mix).
- Auth: `scripts/loadtest_seed.py` mints a forged session cookie
  (`SM_LOADTEST_COOKIE`) so locust skips the login flow and its rate limiter.

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
