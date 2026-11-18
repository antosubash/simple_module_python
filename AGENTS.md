# AGENTS.md

Guidance for coding agents (Claude Code, Codex, Cursor, OpenCode, …) working in this
repository. It holds what changes how code gets written here; history and rationale live
in `docs/`. Claude Code reads it through `CLAUDE.md`, which adds a few Claude-only rules.

## What this is

A **modular-monolith framework**: feature modules are Python packages loaded into
one FastAPI app, each with its own SQLModel tables, REST + Inertia endpoints and
React pages. There is no host–module API boundary.

Stack: Python 3.12 + FastAPI + SQLModel + Alembic; Inertia.js v3 + React +
Tailwind 4 + Vite. `uv` workspaces for Python, `npm` workspaces for JS.
Published as ~23 PyPI packages (`simple_module_*`) and 3 npm packages
(`@simple-module-py/*`) in lockstep (`docs/release.md`).

Layout: `framework/{core,db,hosting,inertia,testing,cli}` (the framework),
`modules/<name>` (plugin modules), `host/` (the dev host app and all Alembic
migrations), `packages/{ui,i18n,tsconfig}` (shared JS), `skills/` (agent skills
shipped to users via `smpy skills add`), `.claude/skills/` (skills for this repo).

## Commands

Everything goes through `make`; the root `Makefile` is the full list
(`docs/reference/make-commands.md` documents the *scaffolded app's* Makefile, not this one).

| Command | Purpose |
|---|---|
| `make install` | `uv sync --all-packages` + `npm install` |
| `make dev` | Shared Docker stack up (needs the sibling `../dev-services` checkout) + `gen-pages` + API (:8000) and Vite (:5050). Without that stack, run `make dev-api` and `make dev-ui` |
| `make test` / `make test-py` / `make test-js` | Pytest (SQLite, e2e/perf excluded; parallel via `pytest-xdist`, `-n $(PYTEST_WORKERS) --dist loadgroup`, default 4 workers, `PYTEST_WORKERS=0` for serial) then Vitest |
| `make test-py-pg` | Pytest on Postgres (`SM_TEST_PG_URL`, default db `sm_test`); parallel like `test-py`, each xdist worker creates its own `sm_test_gw<N>` database (role needs `CREATEDB`); not in `pr-checks` |
| `make test-e2e` | Playwright smoke tests against a running `make dev` |
| `make lint` | Every CI lint check: Ruff format + Ruff + `ty` + Biome + per-workspace `tsc`, package metadata/README, locale files, doc paths, i18n and API-type freshness, file-size cap, no test sleeps, no double casts, no raw `fetch`, hardcoded strings, CI parity, untranslated strings |
| `make doctor` | Module diagnostics (`SM0xx`) |
| `make migrate` / `make downgrade` / `make migration-history` | Alembic `upgrade heads` / `-1` / history |
| `make migration LABEL=<branch_label> msg="..."` | Autogenerate on the selected branch (`--head <branch_label>@head`); `LABEL` is required |
| `make migrations-roundtrip-pg` | Postgres portability gate (upgrade → downgrade base → upgrade → `alembic check`); CI runs it |
| `make gen-pages` | Regenerate `host/client_app/modules.{manifest.json,generated.ts,generated.css}` (gitignored; needed before `tsc`/Vite) |
| `make gen-i18n` | Regenerate `packages/i18n/src/{keys.generated,generated-resources}.ts` (committed; CI diffs them) |
| `make gen-api-types` | Regenerate each module's `pages/api.generated.ts` from its routes (committed; CI diffs via `ci-api-types-fresh`) |
| `make new-module name=<name>` | Scaffold a module package (see § Adding a module for what it does *not* do) |
| `make openapi` | Export `openapi.json` for typed clients |
| `make worker` / `make beat` | Celery worker / beat for `background_tasks` |

Single tests: `uv run pytest path/to/test_file.py::test_name` from the repo root
(`asyncio_mode=auto`, `-m 'not e2e and not perf'` are set in `pyproject.toml`;
`-n` is passed by `make test-py`, not by `addopts`, so this runs in-process);
`npx vitest run <path>` for JS. Entry point: `host/main.py`
(`uv run --project host uvicorn host.main:app --reload`). Alembic runs from the
repo root via `host/alembic.ini`, so it shares `.env`/`SM_DATABASE_URL` with the API.

### Local environment

- **No env var is required.** The default DB is SQLite (`./app.db`), so tests and
  a plain local run need no services. `make dev` starts the author's *shared*
  dev-services stack from `../dev-services/compose.yml` (Postgres on
  `localhost:5432`, db `simple_module_python`; Redis on `localhost:6379`, one
  `SM_REDIS_URL=redis://localhost:6379/4` seeds broker and backend). Never start
  your own Postgres/Redis containers; `make docker-down` only stops this repo's
  worker/beat.
- **Sandboxed sessions have no Docker.** Launch API + Vite directly per
  `.claude/skills/running-the-stack/SKILL.md` (spare ports, SQLite file DB,
  `smpy users create-admin`). `make kill` runs `pkill -f vite` and kills other
  projects' servers, so kill by port instead.
- If a repo-root `.env` exists, read it (don't copy values) and move it aside
  for `make test-py`, then restore it: the `settings` fixture does not pin
  `vite_dev_url`, so a `.env` value leaks into a dashboard test that asserts
  Vite on `:5050`. Never export `SM_ENVIRONMENT=production` in a shell that
  runs pytest: production validators (localhost broker, placeholder secrets)
  abort the test plugin.
- The invalidation tests need `redis-server` on `PATH` or `SM_TEST_REDIS_URL`;
  without either they skip locally and **fail** when `CI` is set.

## Before you push

Run what CI runs, in this order; a red push costs a review cycle.

1. `make gen-pages` once per fresh checkout (generated frontend files are
   gitignored; `tsc` and Vite fail without them).
2. `make lint`. `ruff format --check .` also formats Python fences inside
   `.md` files, so run `uv run ruff format docs/` after editing docs. Every
   backticked repo path in `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/` and
   `skills/` must be a tracked file (`scripts/check_doc_paths.py`; exceptions in
   `scripts/doc_path_allowlist.txt`).
3. `make test-py` and `make test-js`.
4. Touched any `locales/*.json`? `make gen-i18n` and commit the two generated
   files; CI runs the generator and fails on a diff. The generator refuses to
   drop a namespace (an unsynced venv looks like a deleted module);
   `make gen-i18n ARGS=--allow-removals` is only for a module you really
   removed or a deliberate `SM_MODULES_ENABLED` subset.
   Changed an endpoint's response shape in a module that has `pages/api.generated.ts`?
   `make gen-api-types` and commit it. Don't write `as unknown as` in shipped
   TS (`ci-check-no-double-cast`); mark an unavoidable one `// cast-ok: <reason>`.
5. Added a module, a table or a migration? Also run `make doctor`, and review
   the revision per `docs/module-authoring.md` § Reviewing a revision
   autogenerated on SQLite (boolean `server_default` as `sa.true()/sa.false()`,
   expression indexes by hand, enum downgrades via `drop_enums_if_postgres`).
   `make migrations-roundtrip-pg` proves Postgres portability against a
   disposable DB; where no Postgres is available, skip it and let CI run it.
6. User-visible change? Add a `## [Unreleased]` entry to `CHANGELOG.md` (Keep a
   Changelog; cite issue numbers and migration revision ids; mark behaviour
   changes).

CI (`.github/workflows/pr.yml`, aggregate job `pr-checks`): python-lint (the
`make lint` checks above that are not JS), docs-build (`make ci-docs-build`,
the VitePress site), python-typecheck, python-tests (Redis service), js-tests,
js-lint (`biome ci --error-on-warnings`, plus the untranslated check),
js-typecheck (plus `make ci-api-types-fresh`), js-build (`make ci-css-build`),
migrations-roundtrip-pg, doctor (`make ci-doctor`: migrate a throwaway SQLite
DB, `alembic check`, then `make doctor`), e2e-smoke, perf-guards,
file-size-check, package-build. CI calls the same `make ci-*` targets as
`make lint` (`make ci-check-ci-parity` enforces it), with
`UV_SYNC_FLAGS=--locked` so a stale `uv.lock` fails: commit `uv.lock` whenever a
`pyproject.toml` changes (`make install` stays unlocked). `make ci-css-build`
and `make ci-docs-build` are in CI but not in `make lint` (slow).
`.github/workflows/postgres-tests.yml` runs `make test-py-pg` nightly, on
demand and on PRs touching `framework/db`, `framework/testing`,
`modules/{tenants,users,background_tasks,file_storage}` or `host/migrations`;
it is not in `pr-checks`. e2e-smoke and perf-guards enable a hardcoded
`SM_MODULES_ENABLED` JSON list; a new module is not exercised there until added.

## Architecture

**Discovery.** Modules declare `[project.entry-points.simple_module]` pointing
at a `ModuleBase` subclass with `meta = ModuleMeta(...)`.
`simple_module_core.discovery.discover_modules()` loads them, topologically sorts
by `ModuleMeta.depends_on` (plus `optional_depends_on`, ordering only, may be
absent), and the host calls each `register_*` hook in that order
(`docs/framework/discovery.md`). Outside development a missing `depends_on`
target fails the boot (`MissingDependencyError`, `SM030`); selecting
`keycloak` drops `Users`, so modules needing it must be left out.

**Two names per module.** `ModuleMeta.name` (scaffold default: PascalCase,
`FeatureFlags`) keys Inertia render paths, `depends_on` and `SM_MODULES_ENABLED`.
The Python package name (`feature_flags`) keys the i18n namespace,
`app.state.<package>` and table prefixes. Don't swap them: `keys.<ns>` breaks if
the namespace is the meta name.

**Module layout.** Every module uses the area layout below
(`host/tests/test_module_layout.py` enforces it; `docs/module-layout.md` has
the details and the checklist for moving a flat module).

```text
modules/<name>/<name>/
├── module.py, models.py (or models/), contracts/  # entry point, tables, public imports
├── core/                            # constants.py, settings.py, services.py, errors.py
├── web/                             # deps.py, service.py, endpoints/{api,views}.py
├── pages/, locales/                 # lookup paths stay at the root
├── ui/                              # components/, hooks/, utils/ (when needed)
└── tasks.py, task_config.py, cli.py, theme.css, styles.css   # optional
```

Other root directories are allowed only as named domain areas, listed per module
in `DOMAIN_AREAS` in the layout test. Area `__init__.py` files hold only a
docstring. Private helpers stay in their area with a leading underscore. Tests
mirror `tests/<area>/<feature>/`, with no `__init__.py`, unique `test_<name>_*.py`
basenames, no top-level `test_*.py`, and `conftest.py` at `tests/` root. JS
tests stay in `tests-js/`.

`gen-pages` writes `modules.generated.css` with an `@import` per CSS file that
exists. A `@theme` inside a cascade layer is inert and an unlayered rule beats
every Tailwind utility, so keep tokens in `theme.css` and rules in `styles.css`
(`SM022`/`SM023`). See `docs/module-authoring.md` § Styling.

**Lifecycle hooks** on `ModuleBase` (no-op except conventional routes/locales; order and examples in
`docs/framework/lifecycle.md`): `register_settings`, `register_menu_items`,
`register_permissions`, `register_feature_flags`, `register_event_handlers`,
`register_invalidations`, `register_health_checks`, `register_public_routes`,
`register_body_limits`, `register_cors_policies`, `register_rate_limits`,
`register_setup_steps`, `register_csp_sources`, `register_design_packs`,
`register_audit_links`, `register_resource_types`, `register_exception_handlers`,
`register_middleware`, `register_routes(api_router, view_router)`,
`register_admin_routes(admin_router)` (only with `ModuleMeta.admin_view_prefix`),
then async `check_data_compatibility(db)` (read-only upgrade checks before
settings hydration; an `error` refuses boot outside development), then async
`on_startup` / `on_shutdown` (reverse order). Non-hook overrides: `locale_dirs()`,
`db_extensions()`, `template_dirs()`, `static_mounts()`, `spa_mounts()`.

By default, `register_routes` includes `<package>.web.endpoints.{api,views}.router`
when present; import failures inside existing endpoints still fail boot.
`locale_dirs()` discovers `<package>/locales` using the package name as namespace.
`route_prefix` and `view_prefix` default to `""`; declare them explicitly to
mount under a prefix. Omitted `version` comes from the owning distribution
(fallback `1.0.0` without metadata). Explicit versions and hook overrides win.
Keep existing prefixes when adopting conventional routes so URLs do not change.

Rules that go with them:

- A module gets one view router per prefix. All-admin modules point
  `view_prefix` at `/admin/<name>`; modules with both public and admin pages set
  `admin_view_prefix` and use `register_admin_routes`. A prefix is a URL
  convention, not a permission: guard every route.
- `register_public_routes` exempts routes from `AuthMiddleware`, method-aware
  (`registry.add_regex(r"…/tilejson$", methods={"GET"})`):
  `docs/framework/public-routes.md`.
- `register_invalidations` handlers may only *forget* (no delivery guarantee),
  so every cache keeps its TTL as a floor. Publish from a `session.on_commit`
  callback: `await request.app.state.sm.invalidation.publish(channel, key=...)`.
  Cross-process delivery needs the Redis transport `background_tasks` installs
  (`SM_BG_TASKS_BROADCAST_INVALIDATIONS`). `docs/framework/invalidation.md`.
- `register_csp_sources(registry)` takes fetch directives only, validated at
  boot; an origin from DB settings uses `registry.add_provider(fn)`.
- `register_setup_steps`: while a required step is pending, `SetupMiddleware`
  serves the wizard at `/setup`. A step's `SetupAction` runs only while that step
  is pending. `docs/module-authoring.md` § First-run setup steps.
- Events: dispatch keys on the exact class. Durable delivery:
  `bus.subscribe_durable(..., name=...)` (`SM034` without `name=`) +
  `await bus.publish_durable(event, db)` inside the request transaction; a
  durable handler must not commit `ctx.db`. `docs/framework/events.md`.
- Users: read accounts through `get_user_directory(app)`
  (`simple_module_core.user_directory`), never `users.models` outside `users`.
  `DirectoryUser.roles is None` means unknown (Keycloak), not none. Recent
  activity: `get_activity_feed(app)`. `docs/framework/user-directory.md`.
- Menus: `MenuRegistry.add_provider(fn)` for per-request items; permissions:
  `PermissionRegistry.add_source(name, provider)` + `invalidate_source(name)`.
  `docs/framework/permissions.md`.

**Middleware** (Starlette `add_middleware` is LIFO). Execution order per
request: `(ForwardedHost if trusted proxy + allowlist) → (ProxyHeaders if
SM_TRUSTED_PROXY) → (SentryContext if Sentry is enabled) → CorrelationId →
RequestLogging → (ServerTiming, development only) → CORS → BodyLimit → GZip →
SecurityHeaders → Session → InertiaMiddleware → <module middleware> → (Tenant:
multi_tenant, or fixed to default_tenant) → Locale → InertiaLayoutData →
RateLimit → Setup → Maintenance → CommitBeforeResponse → app`
(`framework/hosting/tests/test_middleware_order.py` pins it). Rules that follow:

- Modules at the same dependency tier: the one that sorts later wraps outermost.
  Use `depends_on` to order, never names.
- Any `X-Inertia` response is forced `private, no-store`; to cache a public
  page, set `Cache-Control`/ETag on the *document* response only.
- `RateLimit` runs after auth, so by default it throttles only anonymous
  traffic to public routes. Per-route budgets: `register_rate_limits` rules
  (`RateLimitRule(rate, key="user"|"ip"|"user_or_ip"|"tenant")`) or the
  `RateLimit("10/minute", key="user")` dependency from
  `simple_module_hosting.rate_limit_deps`.
- Request bodies over `max_request_body_bytes` (10 MiB) are refused before any
  module sees them; per-path overrides via `register_body_limits`.
- CORS is opt-in per path (`register_cors_policies`, most specific match wins).
  `docs/framework/cors.md`.

Detail: `docs/framework/middleware.md`, `docs/framework/request-guards.md`.

**Admin section.** Admin screens live under `/admin/*`, register into
`MenuSection.ADMIN_SIDEBAR` and render in `AdminLayout`, all three together.
`SidebarLayout` renders the menu its `menuKey` names, so a page left on
`AuthenticatedLayout` after its item moved shows a sidebar without it.
`group=` sub-clusters inside a sidebar (`Access`, `Appearance`, `System`).
`/admin` itself ships with `simple_module_hosting`; old URLs 301 from
`host/routes_legacy.py`. `/api/*` paths never move.

**Inertia.** `inertia.render("<MetaName>/<Page>")` maps to
`modules/<pkg>/<pkg>/pages/<Page>.tsx`; host pages under
`host/client_app/pages/` use the bare name. Mismatches fire `SM003`/`SM004`.
Use `InertiaDep` from `simple_module_hosting.inertia_deps`; `InertiaResponse`
and prop factories (`optional`, `always`, `defer`, `merge`, `once`, `scroll`)
come from `simple_module_inertia`. Shared props `auth`, `menus`, `i18n` are set
by `InertiaLayoutDataMiddleware`; `auth.user` is null unless
`app.state.principal_serializer` is set (i18n caching via `X-SM-I18n`:
`docs/frontend/shared-props.md`). Inertia
`router.post/patch/put/delete` must target view routes, never `/api/*`
(`SM018`). Fast pages: `docs/frontend/performance.md` and the
`simple-module-page-perf` skill.

**CSRF.** Baseline is `SameSite=Lax` on the session cookie, so a same-site
request needs no token. Defence in depth: `RequiresCsrf` router dependency +
`get_csrf_token(request)` as a view prop, echoed as `X-CSRF-Token`
(`simple_module_hosting.csrf`). The session cookie is `Secure` outside
development and testing.

## Database

- Per-module `Base` via `create_module_base("<name>")`; every module owns its
  `MetaData` but all tables share one schema. Prefix `__tablename__` with the
  module name (`orders_order`); the scaffold does it, nothing enforces it.
- Mixins in `simple_module_db.mixins`: `AuditMixin`, `SoftDeleteMixin`,
  `MultiTenantMixin`, `VersionedMixin`. Soft-delete and tenant filters cover
  every statement shape. Bypass with `execution_options(include_deleted=True)`;
  purge with `hard_delete(session, obj)`. `docs/database/mixins.md`.
- A bare `datetime` field already maps to a UTC-aware type. When you declare
  an explicit column type, use `sa_type=AwareDateTime()`
  (`simple_module_db.types`), never `DateTime(timezone=True)`, which reads back
  naive on SQLite.
- SQLite runs with WAL (file DBs), `busy_timeout` and **`foreign_keys=ON`**:
  both sides of an FK need the same column type (`sa.Uuid` vs fastapi-users'
  `GUID` differ on SQLite) and parents must be flushed before children.
- **Sessions.** The request session (`get_db`) commits in
  `CommitBeforeResponseMiddleware` only if something was written (ORM flush or
  `session.execute(update/insert/delete)`); otherwise it rolls back. Raw
  `text("UPDATE …")` needs `mark_written(session)`. Service and request code
  must not call `session.commit()`; flush when you need DB-assigned values. Use
  `session.on_commit(cb)` for post-commit side effects. `docs/database/sessions.md`.
- **Tenancy fails closed.** With `multi_tenant` on, a query or insert on a
  `MultiTenantMixin` model with no current tenant raises `TenantIsolationError`.
  Cross-tenant code says so with `all_tenants()` /
  `execution_options(all_tenants=True)`; jobs act for one tenant with
  `tenant_context(id)` (both in `simple_module_db.tenancy`). Off, rows are
  stamped `default_tenant` when set, else `DEFAULT_TENANT_ID` (`"default"`).
  Unique keys on tenant tables must include `tenant_id` (`SM024`). Tenant-level
  routes act on the *active* tenant, never a tenant id from the URL. The `tenants`
  module owns memberships and `app.state.tenant_resolver` (`SM025` if missing). Map tenant
  roles with `tenant_role(TenantRole.MEMBER)` from `simple_module_core.tenancy`,
  never by importing `tenants`. `docs/framework/multi-tenancy.md`.
- **Migrations** live in `host/migrations/versions/`, never in module packages.
  `host/migrations/env.py` builds metadata from every installed module. The
  history has several roots and heads (`host/tests/test_migration_graph.py`
  pins them; update it with any new root or head), so apply with
  `upgrade heads` (`make migrate`) and autogenerate on a named branch:

  ```
  uv run --project host alembic -c host/alembic.ini revision --autogenerate \
      -m "<msg>" --head <branch_label>@head
  ```

  A module's first revision sets `branch_labels`. Labels are named targets, not
  per-module rollbacks: `downgrade <label>@base` also unwinds everything above
  and beneath it on that root. `docs/database/migrations.md`.
- Postgres extensions: override `ModuleBase.db_extensions()`; `LTree`/`TSVector`
  types are `TEXT` on SQLite; tests needing Postgres carry
  `@pytest.mark.postgres`. `docs/database/extensions.md`.

## Conventions

- **SQLModel everywhere**: tables are `SQLModel, table=True`; DTOs are plain
  `SQLModel` subclasses. No Pydantic `BaseModel`, no SQLAlchemy
  `DeclarativeBase`/`Mapped[...]` in module code.
- **No magic strings in non-test Python** (`scripts/check_hardcoded_strings.py`):
  `RequiresPermission(...)`, `registry.map_role(...)`, `registry.add_group(...)`
  items, `inertia.render(...)` keys and `depends_on=[...]` entries must be
  constants from `core/constants.py`: `PERM_*`, role names, `_PAGE_*`, `_MODULE_*`.
- **300-line cap** on `.py`/`.ts`/`.tsx`, tests included, untracked files
  included (`scripts/check_file_size.py`). Exempt: shadcn components under
  `packages/ui/src/components/ui/**`, generated i18n files,
  `host/migrations/versions/**`. Split by responsibility; don't squeeze.
- **Configuration lives in the DB, not `.env`.** Operators normally set only
  `SM_DATABASE_URL`, `SM_REDIS_URL` and `SM_USERS_BOOTSTRAP_*`;
  `SM_ENVIRONMENT`/`SM_DEBUG`/`SM_VITE_DEV_URL` describe the process. Do not
  add new configuration as env vars. Host settings: precedence
  **env → DB → default**, and env must keep winning. `host/main.py` uses
  `build_host_app()` from `simple_module_hosting.host`, which calls
  `merge_host_settings()`, not `Settings()`: `create_app` reads some fields
  before the lifespan opens the DB, and every such field is marked
  restart-required (`test_build_time_settings_marked.py`). `SM_SECRET_KEY` is
  optional: unset generates and stores a key; an explicit value wins and is never
  copied into the DB. A pre-app read failure is not a fresh install: outside
  development it refuses to boot (`HostSettingsUnavailableError` /
  `SecretKeyUnavailableError`); only a missing settings table falls back to
  defaults. Stored values parse through `simple_module_core.stored_settings`; an
  invalid row is dropped with a WARNING. Module settings are a
  `DbBackedSettings` subclass registered in `register_settings` through
  `simple_module_core.module_settings.register_module_settings(app, package,
  SettingsCls, services_factory)`, which mounts the services object on
  `app.state.<package>` (`SM012`); this works with the `settings` plugin
  disabled. The exceptions that read env are secrets and process wiring
  (`SM_BG_TASKS_*`, `SM_KEYCLOAK_*`, `SM_USERS_*_TOKEN_SECRET`).
  `docs/framework/settings.md`, `docs/reference/env-vars.md`.
- **Framework must not import plugins** (`SM009`): nothing under `framework/`
  imports from `modules/`; the framework exposes registries and callbacks
  instead. A module may import the modules it lists in `depends_on` directly.
- **Deprecations carry a removal release.** A compat shim uses
  `simple_module_core.deprecation` (`deprecated`, `deprecated_module`, `deprecate`)
  with `remove_in`, and is added to `host/tests/test_deprecation_expiry.py`, which
  fails once the framework version reaches it. No undated "back-compat" shims.
  `docs/framework/deprecations.md`.
- **Background tasks**: `tasks.py` with `@shared_task(name="<module>.<task>")`;
  heavy imports (`torch`, `cv2`, …) inside the task body (`SM028`). Enqueue from
  a transaction with `background_tasks.enqueue_after_commit(db, task, …)`, never
  `.delay()`. Long tasks call `heartbeat()`. `docs/modules/background_tasks.md`.
- **Mail**: build a `MailMessage` and send through `simple_module_core.mail`
  (`current_mail_sender()` in request code, `await resolve_mail_sender(db)` in
  durable handlers). Without the `mail` module the sender only logs. Tests use
  the `captured_mail` fixture.
- **Audit links / design packs**: build links with
  `AuditLink.for_model(Model, url_template=…, …)` (a table-name `entity_type`
  silently never matches); `register_design_packs` slugs must match
  `^[a-z0-9][a-z0-9-]*$` and the host must still import the CSS.
- **i18n.** Ship `<package>/locales/<lang>.json`; the default `locale_dirs()` discovers
  it with the lowercase package name as namespace. Override only for custom paths
  or namespaces; `{"browse": {"title": "X"}}` becomes
  `<ns>.browse.title`; plurals use CLDR suffixes (`_one`, `_other`). Menu items
  set `label_key`/`group_key` beside `label`/`group` (an unresolved key falls
  back to the literal, silently); group headers use `ui.nav_groups.*`.
  **No user-visible string literals in `.tsx`**: JSX text,
  `title`/`placeholder`/`aria-label`-style attributes, `toast.*()`/`confirm()`
  arguments and ternary branches all go through `t(keys.<ns>.…)` from
  `@simple-module-py/i18n`. Exempt: text inside `<code>`/`<pre>`/`<kbd>`/
  `<samp>`/`<var>`, a line marked `// i18n-exempt: <reason>` (or the line
  above), or `i18n-exempt-file: <reason>` within the first 800 characters.
  Strings passed through variables or config objects are not seen, so still
  translate them. Zod schemas with translated messages, and the non-hook `t` in
  helpers, are built inside the function, never at module scope.
  `docs/framework/i18n.md`.
- **Pages call the API through the typed client** (`packages/ui/src/lib/api.ts`,
  built from each module's `pages/api.generated.ts`), not raw `fetch()`
  (`scripts/check_no_raw_fetch.py`); a call that cannot use it is marked
  `// raw-fetch-ok: <reason>`.
- **No fixed sleeps in tests**: poll with `simple_module_test.wait_for`, or mark
  `# intentional-sleep: <reason>` (`scripts/check_test_sleeps.py`).
- **JS tests** go in `modules/<m>/tests-js/*.test.ts(x)`, `packages/**` or
  `host/client_app/**`; Vitest collects nothing else. Biome (single quotes,
  2 spaces, width 100) lints `host/client_app`, `packages`, module `pages/`, `ui/`
  and legacy `components/` dirs; `tsc` runs per workspace, and a module with
  `.tsx` but no `tsconfig.json` fails `make ci-js-typecheck`.
- **`ty` rules.** SQLModel false positives (`unresolved-attribute`,
  `unsupported-operator`, `unknown-argument`, `no-matching-overload`) are
  ignored globally in `pyproject.toml`; don't re-enable them.
  `invalid-argument-type` and `invalid-assignment` are **on** for shipped code
  and ignored only for tests. Fix what they report; for a genuine third-party
  false positive add `# ty: ignore[<rule>]` on that line. Never write
  `# type: ignore[<mypy-code>]`: ty matches the bracket against its own rule
  names, so it suppresses nothing.

## Adding a module or package

There is **one scaffolder**: `make new-module name=<name>` runs
`scripts/new_module.py`, a thin wrapper over the CLI's
`simple_module_cli.scaffolding.create_module(..., framework_repo=True)`, the same
templates `smpy create-module` / `smpy new` use
(`framework/cli/simple_module_cli/templates/module/`). Change a convention there, once.

Settings plumbing is opt-in: `smpy create-module --with-settings` or
`make new-module name=<name> ARGS=--with-settings` adds DB-backed settings,
a services container and `register_settings`; the default omits them.

It generates a CRUD sample (model, DTOs, service, REST + Inertia endpoints,
Browse/Create/Edit pages, `locales/en.json`, tests) that passes `make lint`,
wires the module into `host/pyproject.toml`, the root `testpaths`/`extra-paths`
and the `publish-pypi` matrix in `release.yml`, and runs `uv sync --all-packages`,
`npm install`, `make gen-i18n` and `smpy openapi gen-types --module <name>`.
Commit the resulting `uv.lock`, `package-lock.json`,
`packages/i18n/src/{keys.generated,generated-resources}.ts` and
`pages/api.generated.ts`. It does **not**:

1. Create a migration for the sample table: edit `models.py`, then follow
   § Database (`--head <label>@head`, set `branch_labels` on the first
   revision). `make doctor` reports `SM011` until you do.
2. Register a PyPI pending publisher for the new `simple_module_<name>`
   (manual; the release leg 403s without it).
3. Write `docs/modules/<name>.md`, add it to `docs/modules/index.md` and the
   VitePress sidebar in `docs/.vitepress/config.ts`.
4. Add a `CHANGELOG.md` entry, or add the module to the e2e/perf
   `SM_MODULES_ENABLED` lists if those jobs should exercise it.

A new `framework/*` package is wired by hand: root `pyproject.toml`
`testpaths` + `[tool.ty.environment].extra-paths` and the `publish-pypi`
matrix. A new `packages/*` npm package goes into the `publish-npm` matrix.
Unlisted test directories are silently never collected.

## Diagnostics

`make doctor` and a development boot run the `SM0xx` checks; a dev boot adds
`SM012` and `SM031` (they need the built app), and `SM025` runs at boot in every
environment. The table with triggers and fixes is
`docs/reference/diagnostic-codes.md`. **Production does not run the suite.**
What fails a production boot is strict discovery (a bad entry point, missing
`meta`, or a missing `depends_on` target), the auth-provider check
(`SM020`), placeholder secrets, a localhost Celery broker, the `SM010`
migration check (except on a never-migrated first run, which goes to `/setup`),
overlapping `spa_mounts` (`SM032`) and an `error` from a module's
`check_data_compatibility` (`SM033`). Catch everything else with `make doctor`
before shipping. Codes that change how you write code: `SM003`/`SM004`
render-key mismatch, `SM009` framework→plugin import, `SM011` table missing from
migrations, `SM012` settings not on `app.state`, `SM013`–`SM016` locale drift,
`SM017` module pages without `package.json`/`tsconfig.json`, `SM018` Inertia
call to `/api`, `SM019` views with no menu item or permission, `SM022`/`SM023`
CSS in the wrong file, `SM024` unique key without `tenant_id`, `SM028` heavy
import in `tasks.py`, `SM031` `/api` route with no permission/`Authenticated()`
gate and not public, `SM034` `subscribe_durable` without `name=`.

## Tests & fixtures

`simple_module_test` (`framework/testing/`, auto-loaded via `pytest11`) provides
app-level fixtures to every test directory; the root `conftest.py` is thin.
`docs/testing/fixtures.md`.

- `settings`: in-memory SQLite, `multi_tenant=True`, `auth_provider="users"`.
  `SM_TEST_DATABASE_URL=postgresql+asyncpg://…` switches the whole suite to
  Postgres; `make test-py-pg` uses `-p no:anyio` because an asyncpg connection
  cannot cross event loops.
- `db_state`, `engine`, `db_session`: fresh `DatabaseState` per test;
  `db_session` creates all module tables and stamps `alembic_version` at heads.
- `app`: `create_app(settings)` with lifespan, seeds `admin@test`; `client` /
  `authenticated_client` (`httpx.AsyncClient`, the latter with a forged admin
  session); `tenant_client(role)` for tenant-scoped requests;
  `setup_pending_app`, `fake_event_bus`, `build_test_app`, `redis_server`,
  `captured_mail`.
- `inertia_page(resp)` / `InertiaPage.from_response(resp)` parse an HTML or JSON
  Inertia page for prop assertions and partial/deferred reloads.
- Module-specific fixtures live in each module's `modules/<m>/tests/conftest.py`.
- The plugin drops password hashing to the minimum work factor (hashes stay
  real); pass `password_hash=` or set `SM_TEST_REAL_PASSWORD_HASHING=1` to test
  real parameters.
- The suite runs under xdist, so tests must collect identically in every
  worker: no `uuid4()`/random values in `parametrize` ids, and anything shared
  across processes (a Redis channel, a file) needs a per-worker name.
- E2E lives in `tests/e2e/` behind the `e2e` marker against a live server
  (`docs/e2e-testing.md`); it needs `uv run playwright install chromium` once
  and `SM_RATE_LIMIT_PUBLIC=1000/minute` on the server.

## Working in parallel

Split work into independent slices and run them at once: verification of claims
against code, surveys across many files, test runs per package and adversarial
review are all parallel-safe. Keep sequential what depends on an earlier result.
Give each slice its goal, what is already ruled out, the files to read and the
exact output wanted, and treat every report as claims to verify. Never let two
agents write to one working tree: give a writing agent its own `git worktree`.

## Repo skills

`skills/*/SKILL.md` are the agent skills this repo **ships to users**
(`smpy skills add`, `npx skills add antosubash/simple_module_python`); when a
convention in this file changes, update the matching skill in the same PR.
`.claude/skills/running-the-stack/SKILL.md` is the verified recipe for launching
the stack in a sandbox.

## Authoritative references

When conventions are unclear, read these instead of reverse-engineering code:
`docs/framework-conventions.md` (invariants), `docs/module-authoring.md`
(entry points, migrations, API stability), `docs/framework/*.md` (lifecycle,
middleware, settings, events, i18n, tenancy), `docs/database/*.md`,
`docs/testing/*.md`, `docs/reference/*.md` (make commands, env vars,
diagnostic codes), `docs/superpowers/specs/` (canonical design docs) and
`docs/superpowers/plans/` (implementation plans). `docs/plans/` is historical;
follow status banners and current reference docs rather than dates alone.
