# Configuration to settings, and a first-run setup wizard

**Date:** 2026-08-28
**Status:** Approved, pending implementation plan

## Problem

Standing up a `simple_module_python` app means writing a `.env` by hand before
anything boots. `.env.example` documents roughly thirty `SM_*` variables, and
getting any of the required ones wrong produces a boot failure rather than a
usable screen. That is the whole onboarding experience: edit a file blind, run
the app, read a traceback, repeat.

Most of this friction is already unnecessary. Module settings — SMTP, file
storage, Celery tuning, Keycloak — moved to the DB some time ago and have an
admin UI at `/admin/settings`, a `smpy settings import-from-env` CLI, and a
per-module **Test connection** button. The remaining friction is concentrated
in two places:

1. `BootstrapSettings` still holds thirteen env-only fields, several of which
   have no reason to be env-only.
2. There is no way to configure a fresh install through the browser. The first
   administrator must come from env vars or a shell command.

There is also a live bug worth naming, because it constrains the fix.
`HostSettings` fields (`i18n_*`, `multi_tenant`, `tenant_header`) are declared
DB-backed, but editing them in the admin UI has no effect. See "Two config
epochs" below.

## Goals

- Reduce the env surface to three variables an operator would ever set: a
  Postgres URL (the only genuinely required one), a Redis URL, and an optional
  bootstrap admin. Everything else gets a working default or moves to the DB.
- Any install without a configured administrator presents a setup wizard
  instead of failing or redirecting to a login nobody can pass.
- Connection failures surface during setup, with the reason, while the
  operator is still looking at the form.
- Existing deployments keep working unchanged after upgrade.

## Non-goals

- Writing to `.env` from the running app. Config the wizard collects goes to
  the DB. This keeps the design working on read-only container filesystems and
  avoids a self-restart.
- Multi-tenant onboarding. One install, one setup pass.
- Replacing the existing module settings UI. This work feeds it, not
  around it.

## Two config epochs

`create_app()` is synchronous and consumes configuration in **Phase 1**, before
the database is opened:

```
create_app(settings)                      # ← Epoch A: sync, no DB
  Phase 1  discover_modules(enabled=settings.modules_enabled)
           select_auth_provider(..., settings.auth_provider)
           build_i18n_registry(settings, ...)     # reads i18n_*
  Phase 4  register_settings                       # declares DB-backed classes
  Phase 8  middleware                              # reads trusted_proxy, secret_key
  lifespan:                                        # ← Epoch B: async, DB open
           hydrate_all(...)                        # swaps services.settings
```

By the time hydration runs in Epoch B, the module list, the i18n registry and
the entire middleware stack have already been built from pydantic defaults.
Swapping `services.settings` afterwards changes what a request handler reads,
but cannot rebuild what was already constructed.

This is why `HostSettings.i18n_default_locale` and `multi_tenant` are
effectively inert today: they are consumed at Phase 1 and never re-read.
`maintenance_mode` works only because `MaintenanceMiddleware` reads
`app.state` per request rather than at install time.

Any design that moves `trusted_proxy` or `auth_provider` to the DB inherits
this problem. So the first piece of work is to fix the epoch boundary.

### Pre-app config read

Add a synchronous config read at the top of `create_app`, before Phase 1:

1. Construct `BootstrapSettings` from env as today (this yields
   `database_url`, which is the one thing that cannot come from the DB).
2. Open a short-lived connection and read the host's overrides: rows in
   `settings_setting` at `SYSTEM` scope whose `key` starts with `host.`
   (the store's existing `get_overrides("host")` shape — `key` is
   `"<package>.<field>"`, `value` is always a string, and `value_type` says
   how to parse it).
3. Merge: **env value → DB override → pydantic default**, env winning.
4. Hand the merged settings object to the rest of the boot.

Mechanics: run the read in a dedicated thread with its own event loop
(`ThreadPoolExecutor` + `asyncio.run`). This is safe whether or not the caller
already has a running loop — `create_app` is called synchronously by uvicorn
but inside a running loop by parts of the test suite — and it reuses the
existing async driver rather than requiring a second, synchronous one
(`asyncpg` cannot be driven from a sync engine).

The read must degrade gracefully in three cases, all of which occur on a
genuinely fresh install:

- **DB unreachable** — fall back to defaults, let the app boot into setup mode
  so the wizard can report the connection failure. Do not fail the boot.
- **DB reachable but not migrated** — `settings_setting` does not exist yet.
  Catch the missing-table error specifically, fall back to defaults.
- **Table exists but empty** — normal, defaults apply.

Failing the boot in any of these cases would defeat the wizard entirely, since
the wizard is what fixes them.

## Env surface

### Kept in env

| Variable | Required | Rationale |
|---|---|---|
| `SM_DATABASE_URL` | yes | Needed to open the DB. Cannot be DB-backed. |
| `SM_REDIS_URL` | no | New. The Celery worker process has no `app.state` and cannot hydrate from the DB, so it needs an env source. Defaults to localhost. |
| `SM_ENVIRONMENT` | no | A deploy fact, not configuration. Drives strict discovery and prod validators. |
| `SM_DEBUG` | no | Process fact. |
| `SM_VITE_DEV_URL` | no | Dev-loop only, ignored in production builds. |
| `SM_USERS_BOOTSTRAP_EMAIL` / `_PASSWORD` | no | Optional. Their absence is what triggers the wizard. |
| `SM_PROJECT_ROOT` | no | Path anchor resolved before any settings exist. |

### Moving to DB-backed, env still overriding

`trusted_proxy`, `log_level`, `log_format`, `auth_provider`,
`auth_public_paths`, `db_pool_size`, `db_max_overflow`, `db_pool_pre_ping`,
`db_pool_recycle`.

The four pool fields are marked `requires_restart=True` through the existing
`json_schema_extra` idiom already used by `BackgroundTasksSettings`, because
the engine is constructed once at boot. The admin UI already renders that
marker.

### Redis consolidation

`SM_BG_TASKS_BROKER_URL` and `SM_BG_TASKS_RESULT_BACKEND` collapse into a
single `SM_REDIS_URL`. Celery namespaces result keys as `celery-task-meta-*`,
so a broker and a result backend can share one Redis database safely — this is
the configuration upstream's own quickstart uses. Both underlying fields keep
individual DB overrides for anyone who wants them split across databases.

`SM_BG_TASKS_BROKER_URL` and `SM_BG_TASKS_RESULT_BACKEND` remain functional as
deprecated aliases that log a warning on use. They are set in `smpy_gis`,
`smpy_saas`, `laco_wiki_python` and the `nodes-k8s` manifests; breaking them
outright would break those deployments on upgrade for no benefit.

### Secret key

`SM_SECRET_KEY` becomes optional. Resolution order:

```
env SM_SECRET_KEY  →  DB host.secret_key  →  generate, store, use
```

Generation must be atomic: `INSERT ... ON CONFLICT DO NOTHING` followed by a
re-read of whatever actually landed. Two web workers booting concurrently
against an empty DB would otherwise mint different keys and continuously
invalidate each other's sessions — an intermittent "randomly logged out" bug
that would be extremely unpleasant to diagnose.

The existing production validator that rejects the placeholder value stays,
but now only fires when a key is explicitly set to the placeholder string,
not when one is absent.

## Setup mode

### Gate

A new `SetupRegistry` in `framework/core/simple_module_core/`, with a
`register_setup_steps(registry)` hook on `ModuleBase`, following the idiom
already established by `register_public_routes` and `register_csp_sources`.

A step declares an id, a title, a description, and an `is_complete()`
predicate. Registered steps:

- `users` → *"an administrator exists"*
- host → *"database migrated"*

The gate must be a hook rather than a hardcoded superuser count because of
Keycloak. When Keycloak is the active auth provider there is no local admin
table to count, so it registers no step and the gate never engages. A
hardcoded check would lock every Keycloak install out of its own application
permanently.

While any required step is incomplete, `SetupMiddleware` redirects all
requests to `/setup`, exempting `/setup` itself, `/static`, and `/health`.

Completion is **recomputed on each request, not stored as a one-way flag**.
This was a deliberate choice: an install that loses its administrators can be
recovered through the browser rather than requiring shell access to the
container. The tradeoff is that deleting every admin on a live install reopens
setup — acceptable, because an install with no administrator is already
non-functional.

### Connection testing

The per-module **Test connection** button and its `HealthRegistry` backing
already exist, and already return real diagnostic detail — distinguishing
"connection refused" from "authentication failed", which is the distinction
that matters because the two need different fixes. The wizard calls the same
endpoint rather than growing a parallel implementation.

Two health checks are missing and need to be written. Both are useful
independently of setup, since they also feed the readiness probe:

- **host → database**: `SELECT 1`, plus migration revision status.
- **background_tasks → Redis**: broker `PING`, plus result-backend
  reachability.

### Wizard flow

Host-owned Inertia pages at `/setup`. Unauthenticated by necessity — it exists
precisely when no account exists yet — and self-disabling the moment all
required steps complete.

1. **Connections.** Live pass/fail for Postgres and Redis via the health
   checks, showing the failure reason. Re-testable without a page reload.
2. **Migrations.** When `check_migrations` reports behind-head, an "Apply
   migrations" button.
3. **Administrator.** Email and password, delegating to the existing
   `users.bootstrap.create_admin`.
4. **Site basics.** Site name, default locale, auth provider, written to
   DB-backed host settings.

**On step 2:** this was flagged during design as a scope decision and approved
as part of the whole. Today an unmigrated database fails production boot with
`SM010` and drops the operator to a shell, which is the sharpest remaining
onboarding edge. Including the step removes it, at the cost of a web endpoint
that can run Alembic. The endpoint is reachable only while setup mode is
active — that is, only before any administrator exists — so it closes off
permanently once the install is configured. If this tradeoff is unwanted, this
step can be struck without affecting the other three.

## Testing

Existing fixtures (`settings`, `db_session`, `app`, `authenticated_client`)
cover most of the surface. New coverage:

**Pre-app config read**
- A DB override beats the pydantic default.
- An env value beats a DB override.
- An unmigrated DB falls back to defaults without raising.
- An unreachable DB falls back to defaults without raising.
- Concurrent boots against an empty DB converge on a single secret key.

**Setup gate**
- Redirects to `/setup` while a required step is incomplete.
- Releases once all steps complete.
- Never engages when Keycloak is the active auth provider.
- `/static` and `/health` stay reachable during setup.

**Health checks**
- DB and Redis checks report healthy against live services, and report the
  specific failure reason against a wrong host and against bad credentials.

**Deprecation**
- `SM_BG_TASKS_BROKER_URL` still configures the broker and logs a warning.

**E2E**
- A fresh database reaches a logged-in dashboard without `.env` ever being
  edited beyond the two required variables.

## Risks

- **Migration ordering.** `settings_setting` must exist before the pre-app
  read can return anything, so on a genuinely empty database the read always
  falls back to defaults. That path is the common first-boot case and must be
  tested directly, not assumed to work.
- **Precedence regressions.** Env must keep winning over DB. If that inverts,
  existing production deployments silently change behaviour on upgrade — the
  worst possible failure mode for this work, because nothing errors.
- **Alembic over HTTP.** Mitigated by the endpoint being reachable only during
  setup mode, but it is a real widening of the attack surface on an
  unauthenticated route. The step is optional and separable.
- **Scope.** This touches `BootstrapSettings`, `create_app`, the middleware
  pipeline, `background_tasks`, `users`, and adds a host route group. It
  should land as a sequence of independently reviewable changes, not one
  commit.

## Sequencing

The pre-app config read is a prerequisite for everything else and fixes a
standing bug on its own, so it should land first and separately.

1. Pre-app config read + `HostSettings` fields becoming genuinely live.
2. Move the nine fields out of `BootstrapSettings` to DB-backed.
3. `SM_REDIS_URL` consolidation with deprecated aliases.
4. Optional secret key with atomic generation.
5. DB and Redis health checks.
6. `SetupRegistry`, hook, and middleware.
7. Wizard pages.
8. Docs: `.env.example`, `CLAUDE.md`, `docs/framework-conventions.md`.
