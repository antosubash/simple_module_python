# Navigation performance: measure, then fix

**Date:** 2026-08-02
**Status:** approved, pending implementation plan

## Problem

Page navigation feels slow. No measurement exists to say why, where, or by how
much. The complaint is about *navigation* — click to painted page — and nothing
in the repo measures that.

## What already exists

The backend has had a perf pass. Relevant prior commits:

| Commit | Change |
|---|---|
| `fef0959` | Cut redundant auth/list query loads; fixed production Inertia rendering + asset caching |
| `878f51f` | `users` list via column query instead of full ORM hydration |
| `026c146` | `audit_log` list via column query, dropped count subquery |
| `80bcd90` | Stopped loading `oauth_accounts` on every authenticated request |
| `00d303d` | Dropped `EmailStr` from response schemas (re-validation waste) |
| `984443b` | Vite content-hashed assets cached immutably |

Existing harness:

- `tests/loadtest/` — locust (`AuthedUser` weighted browse scenario), faker seed,
  forged-session-cookie auth that skips the login rate limiter.
- `tests/benchmarks/` — pytest-benchmark, behind the `perf` marker.
- `make memray-run` / `make loadtest-memray` — allocation profiling + flamegraph.
- `make bench`, `make loadtest`, `make loadtest-seed`.

Auth is already session-cached (`modules/users/users/provider.py:40`) and i18n
message snapshots are built once at load, handed out by reference
(`framework/core/simple_module_core/i18n.py:171`).

**Conclusion: the cheap backend wins are largely taken.** The remaining problem
is unlikely to be where intuition points, which is why this spec measures before
it changes anything.

## Gap

Nothing measures Inertia navigation. Specifically, no test captures:

- Server TTFB for an `X-Inertia: true` request.
- Per-navigation response payload size.
- Client-side render time from response received to content painted.
- Total click → painted, which is the metric the complaint is actually about.

## Suspects (hypotheses to validate, not conclusions)

These come from reading the request path. Each is a hypothesis. None is acted on
until measurement ranks it.

### S1 — Shared props built for requests that discard them

`framework/hosting/simple_module_hosting/middleware.py:237`

`InertiaLayoutDataMiddleware.__call__` runs on **every** HTTP request. For an
`/api/*` JSON request it builds `menus`, expanded frontend `permissions`, the
`i18n` block, and runs every registered shared-prop provider — then the response
never uses any of it.

Note the constraint: `request.state.resolved_permissions` **is** consumed by
`RequiresPermission` on API routes, so that computation must stay. Only the
frontend-facing expansion, menus, i18n block, and providers can be skipped.

### S2 — Per-request recomputation of pure functions

`middleware.py:257` and `framework/core/simple_module_core/menu.py:66`

- `expand_permissions` runs `sorted(set(all_permissions))` on every request for
  any wildcard (admin) role.
- `MenuRegistry.get_for_user` rebuilds every menu item dict on every call.

Both are pure functions of `(is_authenticated, roles)`. Neither is cached.

### S3 — Full shared-prop payload on every navigation

`middleware.py:268`

`auth.permissions` and `menus` ship in full on every Inertia navigation. Inertia
does not dedup shared props across navigations, so this is fixed per-navigation
overhead that grows with the number of registered permissions and menu items.

**S3 is the leading candidate** for the reported symptom, but it is not assumed.

### S4 — Dev-vs-prod confound

In `make dev`, each newly visited page triggers a Vite transform round-trip.
Pages are already code-split lazily (`host/client_app/pages.ts`), so first visit
to a route pays a network + transform cost that production does not. Measuring
only dev would mistake a dev-mode artifact for a production problem; measuring
only prod would miss real daily-driver friction. Both are measured, separately.

## Goals

1. A repeatable navigation benchmark producing a baseline number per route.
2. Evidence-ranked optimization: every change lands only if it moves a measured
   number.
3. Before/after figures for each optimization applied.

## Non-goals

- k6. The existing locust harness is used instead (explicit user decision).
- Rewriting the frontend rendering approach.
- Optimizing anything without a measurement backing it.

## Decisions

| Decision | Choice |
|---|---|
| Environments | Both dev and production build, measured separately |
| Database | Postgres via shared `dev-services` stack, throwaway `smpy_loadtest` DB |
| Sample entity | Rich — relations, search, enum, mixins |
| Load tool | locust (existing harness), extended. Not k6. |
| UI tool | Playwright |

## Components

### C1 — `modules/catalog` sample module

Scaffolded with `make new-module name=catalog`. A rich entity that exercises the
realistic worst case:

- FK relation to a category table.
- Indexed text field for search.
- Enum status field.
- Timestamps via `AuditMixin`; `SoftDeleteMixin`.
- `catalog_product` / `catalog_category` table names (module-prefixed, per
  convention).
- First migration sets `branch_labels = ("catalog",)`.
- List page with search + filter + sort + pagination; detail page.
- Locales, permissions, menu entry — full convention compliance so the module
  doubles as a reference implementation for module authors, which the repo
  currently lacks.

### C2 — Seed

Extends `tests/loadtest/seed.py`. Faker-generated, idempotent, `--force` to wipe
and re-seed, matching the existing seed's contract. ~5k products across
categories. Target is the throwaway `smpy_loadtest` Postgres database per
`tests/loadtest/README.md`. `ANALYZE` after seeding so query plans are real.

### C3 — Playwright navigation benchmark

New, under `tests/perf/`. Marked `@pytest.mark.perf` **and** `@pytest.mark.e2e`
— it is both a benchmark and a live-browser test, and the existing default
`addopts` (`-m 'not e2e and not perf'`) then excludes it without needing a new
marker. `tests/perf` is added to `testpaths`.

It gets its own make target (`bench-nav`) rather than folding into `make bench`,
because `make bench` targets `tests/benchmarks` and runs in-process, while this
requires a live server and a browser.

Instrumentation hooks Inertia's own router events (`router.on('start')` /
`router.on('finish')`) plus paint timing, capturing per navigation:

- Server TTFB for the `X-Inertia` request.
- Response payload bytes.
- Client render duration.
- Total click → painted.

Runs the same route set against dev and production builds so the Vite-transform
component (S4) is isolated from cost that ships to users.

### C4 — Locust extension

Adds catalog list / search / detail tasks to the existing
`tests/loadtest/locustfile.py` `AuthedUser` scenario, using the same `name=`
grouping convention so paginated URLs don't explode the stats table.

### C5 — Micro-benchmarks

Added to `tests/benchmarks/` using the existing pytest-benchmark setup, covering
the shared-props build path. Gives a fast regression signal on middleware
changes without needing a full load test.

## Method

1. Build C1–C5.
2. Take a baseline across all routes, dev and prod.
3. Rank suspects by measured contribution.
4. Fix highest-ranked first. Re-measure after each fix in isolation.
5. Stop when remaining candidates cost more than they return.

A fix that does not move a measured number is reverted, not kept on the theory
that it "should" help.

## Testing

- Existing suites must stay green: `make test`, `make lint`, `make doctor`.
- The new `catalog` module ships its own tests, following the conventions in
  `docs/module-authoring.md`.
- `make doctor` must report clean for `catalog` — in particular `SM003`,
  `SM004`, `SM011`, `SM017`, `SM019`.
- Benchmarks are excluded from the default `pytest` run by marker, consistent
  with existing `perf` / `e2e` handling.

## Risks

| Risk | Mitigation |
|---|---|
| Benchmark noise swamps the signal | Multiple runs; report median and spread, not single numbers |
| Optimizations regress correctness | Full suite green after each change; changes land individually, not batched |
| Caching shared props leaks data across users | Cache key must include every input that varies the output (`is_authenticated`, roles). Explicit test for cross-user isolation before any caching lands. |
| `catalog` ships as a demo module in the tree | It is a genuine reference implementation. Can be excluded from the default enabled set via `SM_MODULES_ENABLED` if unwanted. |
| Dev-mode findings mistaken for prod problems | Dev and prod measured and reported separately throughout |

## Success criteria

1. A baseline report exists, per route, dev and prod.
2. Every optimization applied cites a before/after number.
3. Measured improvement in total click → painted on the production build.
4. `make test`, `make lint`, `make doctor` all clean.
