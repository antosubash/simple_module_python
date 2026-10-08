# Backend load test on Postgres

**Date:** 2026-10-08
**Harness:** [tests/loadtest/](../../tests/loadtest/README.md) (locust + faker seed)

## Environment

| | |
|---|---|
| Machine | linux, 24 cores, shared `dev-services` Postgres (Docker, `max_connections=100`) |
| Database | Postgres, fresh DB, 10 000 users (9 000 role assignments), 100 000 audit rows, `ANALYZE`d |
| Modules | `Auth, FeatureFlags, Settings, FileStorage, Users, AuditLog, BackgroundTasks, Dashboard, Permissions, Tenants, SiteLock, Branding` |
| Server | `uvicorn host.main:app`, development mode, one worker unless stated |
| Load | `locustfile.py` `AuthedUser` mix, 300 users, spawn 100/s, 60 s |
| Micro | in-process `httpx.ASGITransport`, sequential, 200 warm requests per URL, median |

## Saturated throughput (300 users, 1 worker)

| | req/s | p50 | p95 | failures |
|---|---:|---:|---:|---:|
| Before | 117.7 | 330 ms | 9.7 s | 1 (`QueuePool limit … reached`) |
| After | 123.5 | 330 ms | 9.5 s | 3 |
| After, `SM_DB_POOL_PRE_PING=false` | 127.1 | 310 ms | 9.8 s | 1 |
| After, 4 workers, pool 5 + 10 | **520.9** | **180 ms** | **790 ms** | **0** |

One worker is **CPU-bound**: the process sat at 98% of one core while
Postgres used about one core. The p95 of ~10 s is queueing, not slow
queries. Weighting each endpoint's measured CPU by the locust mix gives
~8.7 ms per request, a ceiling of ~115–125 req/s on one core, which matches what
was observed. Behind a saturated event loop each request holds its pooled
connection far longer than its queries take, so the pool (10 + 20) runs dry
and requests wait up to `pool_timeout` (30 s).

So throughput is a deployment lever, as in the June campaign: four workers
with the pool cut so that `workers × (pool_size + max_overflow)` stays under
`max_connections` gave 4.4× the throughput and a 12× better p95 with no
errors. See `docs/reference/deployment.md`.

## Per-request cost (in-process, ms, median)

Wall time; the DB-backed rows include Postgres round-trips and are noisy on the
shared instance.

| URL | before | after |
|---|---:|---:|
| `/health` | 1.98 | 1.46 |
| `/api/feature_flags/` | 2.19 | 1.90 |
| `/api/permissions/` | 3.00 | 2.52 |
| `/api/dashboard/stats` | 2.53 | 2.12 |
| `/dashboard/` (Inertia) | 3.67 | 3.24 |
| `/admin/users/` (Inertia) | 28.9 | 25.3 |
| `/api/users/admin` | 11.2 | 11.0 |
| `/api/audit_log/` | 22.0 | 24.1 |
| `/api/settings/modules` | 8.58 | 8.13 |

Main-thread CPU for the heavy endpoints: `/admin/users/` 17.5 ms,
`/api/users/admin` 10.5 ms, `/api/audit_log/` 8.4 ms, `/api/settings/modules`
8.1 ms. These make up most of the mix's CPU.

## Fixed

1. **Route matching was ~30% of a cheap request's CPU.** FastAPI ≥ 0.140
   keeps every `include_router` as a lazy `_IncludedRouter`. The app root
   holds ~35 of them (one API and one view router per module), and none
   filters on its prefix, so a request regex-tested nearly all ~190 routes. It
   also re-walked each subtree's route version and ran `_match` twice on the
   router that matched. `simple_module_hosting._route_guard` gives each
   top-level include a prefix guard derived from its effective route paths and
   re-derived when FastAPI's route version changes. Saves ~0.5 ms per request.
2. **Cold start.** The first request to reach a router builds every one of its
   routes' dependants (signatures and pydantic adapters). The guards are built
   at lifespan start, which does that work during boot: the first request
   dropped from 360 ms to 32 ms, and startup grew by about the same amount.
3. **GZip at level 9.** Starlette's default. A 76 KB first-load page cost
   6.4 ms of event-loop CPU at level 9 against 2.7 ms at level 5, for 1.2%
   less output. Now level 5.
4. **Setup-gate stampede.** The verdict TTL (5 s) lapsing under load made
   every in-flight request run `has_administrator` on its own pooled
   connection, which fed the pool exhaustion. Now single-flight, and an
   expired *complete* verdict answers while the refresh runs.
5. **Threadpool hops.** Trivial sync dependency getters made FastAPI dispatch
   each one to the threadpool. They are now `async def`.
6. **`/admin/users/` status cards** issued three `COUNT(*)` round-trips; now
   one `COUNT(*) FILTER (WHERE …)` scan.

## Not changed: findings and follow-ups

- **`pool_pre_ping`** runs `BEGIN; ; ROLLBACK` (three round-trips) on every
  checkout. That is ~1.4 ms of held-connection time per DB request against a
  331 µs bare round-trip, plus ~4.5% of request CPU. Turning it off gave +3%
  throughput. It stays on by default, since it is what lets a pool survive a
  database restart, but a host with a stable database and its own retry layer
  can set `SM_DB_POOL_PRE_PING=false`.
- **Soft-delete/tenant statement filter** (`query_filter.filter_statements`)
  attaches `with_loader_criteria` for every soft-delete model to every SELECT
  and walks subqueries: ~0.35 ms of CPU per statement. Compiled-cache hits
  are unaffected (every statement measured was a `CACHE_HIT`). It is the
  isolation boundary from #332, so it needs a design-level review rather than
  a perf patch.
- **Audit-log `COUNT(*)`** over 100k rows takes ~15 ms on this instance and
  dominates `/api/audit_log/`. An estimated or capped count would be a UX
  decision.
- **`/api/settings/modules`** spends ~8 ms rebuilding the view of ~110
  settings fields per call. It is a low-traffic admin screen that the mix
  over-weights, and its output depends on live env, DB overrides and secret
  masking, so it is left uncached.
- Inertia payloads: the first navigation per session carries the full i18n
  catalog (~75 KB of a 76 KB page); later navigations send 4.3 KB. A client
  without a cookie jar (curl) sees 76 KB every time, so measure with one.
