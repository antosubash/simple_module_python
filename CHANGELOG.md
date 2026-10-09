# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/) post-1.0.

> **Coverage note.** Between 0.0.1 and 0.0.27 this file carried no per-version
> sections, and several already-released fixes sat under `[Unreleased]` long
> after shipping — which led a downstream app to conclude a fix it depended on
> was still unreleased (GH issue #253). Those entries have been moved to the
> release they actually shipped in, verified with `git tag --contains`.
> Versions not listed below still have no entry; consult the commit log.

## [Unreleased]

### Added
- **Host override layer for module copy** (#415). A host ships
  `host/locales/overrides/<lang>.json` (nested or flat dotted keys) and it is
  applied after every module, framework and host catalog, so the server-side
  `Translator`, menus and Inertia props all see it. An override only replaces an
  existing key: an unknown key is skipped with a warning and reported by
  `make doctor`. Admin-only keys stay admin-only.
- **Public tenancy API** (#418): `simple_module_hosting.tenancy` exposes
  `tenancy_mode(app)`, `single_tenant_id(app)`, `require_tenant(...)` (binds
  the single-tenant id, or the request's tenant else `on_missing`) and
  `tenant_vary(request)`; `TenancyMode` lives in `simple_module_core.tenancy`.
  Modules no longer need to read the middleware stack.
- `NativeSelect` takes a `wrapperClassName` for sizing the control (#421).
  `className` still targets the `<select>`.
- **The `/setup` wizard ships with the framework** (#351). Since 0.0.33
  `SetupMiddleware` redirected a fresh install to `/setup`, but the route and
  page lived only in this repository's unpublished host, so any other host got
  `/` → `/setup` → 404. `create_app` now mounts the wizard
  (`simple_module_hosting.setup_wizard`) and `gen-pages` registers its page
  (`Setup/Wizard`) from the wheel; a host needs no setup code and should delete
  any copy it carries. Steps complete from the browser through a new
  `SetupStep.action` (`SetupAction` / `SetupField` in `simple_module_core`),
  POSTed to `/setup/steps/<id>` with the session CSRF token. An action runs only
  while its own step is pending (409 otherwise); `users` ships the
  first-administrator action, which re-checks under a database lock inside the
  inserting transaction so concurrent requests create one superuser. Required
  steps without an action are logged at boot. The old host-only
  `/setup/administrator`, `/setup/migrations` and the UI-less
  `/setup/site-basics` endpoints are gone.
- **Postgres test runs** (#343) — `SM_TEST_DATABASE_URL` points the
  `simple_module_test` fixtures at Postgres, and `make test-py-pg` runs the
  whole Python suite there. The schema is reset once per test, so `app` and
  `db_session` see each other's rows as they would in production.
- **`tenants` module** — SaaS organisations: tenants, many-to-many memberships
  with per-tenant roles (`owner`/`admin`/`member`, surfaced as `tenant:<role>`
  on the active tenant only), email-bound invitations, platform suspend /
  reactivate, and the membership-validated tenant resolver. Ships the seams a
  billing module needs: an `EntitlementProvider` on
  `app.state.tenants.entitlements` (seat limits enforced, HTTP 402), lifecycle
  via `TenantService.set_status`, and after-commit domain events. See
  [docs/framework/multi-tenancy.md](docs/framework/multi-tenancy.md).
- `simple_module_db.tenant_context()` / `all_tenants()` and the
  `all_tenants=True` execution option, for acting as one tenant — or
  deliberately across tenants — outside a request.
- `TenantMiddleware` consults `app.state.tenant_resolver` when a module
  registers one.
- `background_tasks` carries the enqueuing request's tenant into the Celery
  task and restores it around the task body.
- Doctor check `SM024`: a unique key on a `MultiTenantMixin` table that omits
  `tenant_id`.

- `InvalidationBus` — a framework-level cache-invalidation channel any module can
  publish on (`ModuleBase.register_invalidations`, `app.state.sm.invalidation`).
  In-process by default; `background_tasks` installs a Redis pub/sub transport on
  the connection it already configures, so a write drops the matching entry in
  *every* worker instead of only the one that performed it.
  Turn it off with `SM_BG_TASKS_BROADCAST_INVALIDATIONS=false`; rename the channel
  with `SM_BG_TASKS_INVALIDATION_CHANNEL` for every app on a shared Redis server
  (pub/sub ignores the database index, so DB 4 vs DB 5 does not isolate it).
  See [docs/framework/invalidation.md](docs/framework/invalidation.md) (GH #318).
- `users` publishes its `session_version` bump on that bus, so "sign out
  everywhere" and a password change stop being honoured across every worker at
  once rather than after each worker's `users.session_version_cache_ttl_seconds`
  window. The TTL now bounds a *dropped* message rather than every cross-worker
  revocation; installs without a reachable Redis keep the previous behaviour.
- Request-scoped database sessions now expose `session.on_commit(callback)` for
  synchronous or asynchronous cache refreshes and other derived state. The
  framework invokes callbacks only after a successful commit and discards them
  on rollback or commit failure.
- Every `smpy new` scaffold now ships Docker assets by default: a multi-stage
  `docker/host.Dockerfile` (uv + Node builder that runs `gen-pages` before the
  Vite build, slim non-root runtime that applies migrations on start), a
  `docker-compose.yml` matched to the `--db` choice (`app` on a SQLite named
  volume, or `postgres` + `app` — migration histories are dialect-frozen at
  autogenerate time, so containers run the same DB the migrations were
  generated against), plus `redis`/`worker`/`beat` reusing the app image when
  `background_tasks` is selected, a `.dockerignore`, and `make docker-up` /
  `docker-build` / `docker-down` targets. Previously Docker files only
  appeared with `background_tasks`, and their frontend stage couldn't build
  real apps (no `gen-pages` step). The separate `worker.Dockerfile` is gone;
  worker/beat run the same image with a celery command. `smpy new` also
  generates real `SM_USERS_*_TOKEN_SECRET` values into `.env.example` so the
  production-mode containers pass `UsersSettings` boot validation.

### Changed
- `TenantMiddleware` now varies on `Cookie` when the tenant came from the
  session, and on `Cookie, Authorization` when it came from an authentication
  claim, so a shared cache can no longer serve one tenant's response to another
  (#418).
- **Tenant isolation fails closed.** With `multi_tenant` on, a query, bulk
  `update()`/`delete()` or insert on a `MultiTenantMixin` model with no tenant
  context raises `TenantIsolationError` instead of reading or writing every
  tenant's rows. ORM `update()`/`delete()` are now tenant-scoped too; they were
  not before.
- Changing a row's `tenant_id` is refused whether or not a tenant is bound
  (it used to be checked only inside a tenant context); only an `all_tenants()`
  block may move a row between tenants.
- Tenant rules now cover every ORM write path, not only `session.add`: an
  ORM `insert(Model)` (bulk or `.values()`) is stamped with the bound tenant
  and refused for a different one (#357); `update(Model).values(tenant_id=…)`
  is refused; a flush that writes or deletes an object belonging to another
  tenant (e.g. one returned from the identity map after a `tenant_context`
  switch) is refused.
- `tenant_context()` nested in `all_tenants()` now scopes its block; it used
  to be ignored there, so a per-tenant loop inside a platform job ran
  unscoped.
- Strict mode is held per engine, so a second `DatabaseState` in the process
  no longer switches it off for the first. The Celery worker's session gets the
  tenant listeners and the host's `multi_tenant` setting too (#371).
- New `MissingTenantError` (a `TenantIsolationError`) for "no tenant bound".
- Tenant and soft-delete criteria reach join targets, subqueries (including a
  bare Core `exists().where(...)`), `count().select_from()` and top-level Core
  statements on `Model.__table__` (#332). **Behaviour change:** a join or count
  over a soft-deletable model now excludes trashed rows, as a plain `select`
  already did; `include_deleted=True` still reveals them.
- `HostSettings.default_tenant`: single-tenant hosts run mixin tables as one
  tenant (#359). `bind_current_tenant(fn)` carries the tenant into work a
  module defers past the request (#364). The `tenants` module resolves a
  tenant from the subdomain (`subdomain_base`), anonymous visitors included
  (#363).
- **Request-path performance** (Postgres load test,
  [docs/perf/2026-10-08-postgres-loadtest.md](docs/perf/2026-10-08-postgres-loadtest.md)).
  Route matching skips any included router whose routes cannot match the path:
  FastAPI ≥ 0.140 regex-tested nearly all ~190 routes per request, ~30% of a
  cheap request's CPU (`/health` 1.98 → 1.46 ms). The guards are built at
  startup, which also takes FastAPI's lazy per-route build off the first
  request after boot (360 → 32 ms). GZip runs at level 5 instead of 9: about
  1% larger output for 2.4× less CPU. Trivial sync FastAPI dependencies
  (`get_permission_registry`, `get_feature_flag_registry`, the `file_storage`,
  `tenants` and `users` accessors) are now `async`, so they no longer
  take a threadpool round-trip. `/admin/users` counts its status cards in one
  query instead of three.
- `SetupMiddleware` refreshes its cached verdict single-flight. When the 5 s
  TTL lapsed under load, every in-flight request ran the setup steps itself,
  each checking out a pooled connection. Behind a saturated pool those
  checkouts queued and fed `QueuePool limit … reached` timeouts. The expired
  *complete* verdict now keeps answering while one refresh runs.

### Security
- The tenant header (`tenant_header`) is no longer honoured for an
  authenticated user without a tenant of their own: such a user could name any
  tenant. On the legacy path it applies to anonymous requests only; with the
  `tenants` resolver it selects among the user's own memberships.

### Fixed
- `/admin/background-tasks` returned 500 on Postgres (#413): `TaskExecution`'s
  timestamps were declared naive although the columns are `timestamptz` since
  `e5f2a8c1d7b3`. This was already fixed on `main` by #406 (unreleased since
  v0.0.35); this branch only pins it with tests. No migration.
- Sign-in aside footer text met only 2.7:1 contrast; `--color-dark-text-subtle`
  is lighter and clears WCAG AA (#414).
- Only top-level navigations record the post-login target (#416): a favicon,
  script, image or `fetch()` hitting an unauthenticated route no longer
  overwrites it. Navigations and Inertia visits record the target as before;
  requests that carry no fetch metadata keep the old behaviour.
- The tenant filter no longer turns an outer join into an inner join when the
  joined table is only referenced inside a function such as
  `func.count(Child.id)` (#417), whether it joins the entity or a relationship
  path (`.outerjoin(Parent.children)`, with or without `of_type`). A raw-table
  target or a `secondary` relationship stays filtered in `WHERE`, so this never
  leaks another tenant's rows.
- `gen-pages` emits `@source` lines for subdirectories of wheel modules (#419);
  uv's `.venv/.gitignore` made Tailwind skip them, so their utility classes
  were missing from the built CSS.
- Brand foreground ink follows the brand colour (#420): `deriveBrandRamp` sets
  `--primary-foreground` and `--sidebar-primary-foreground` by WCAG contrast
  (white or dark ink), so buttons and the active sidebar row stay legible on a
  light brand colour; the logo badge initial stays white on the ramp gradient.
- Admin screens (#422): `/admin/users/` has a document title, `/admin/settings/`
  has a visible `<h1>`, and error pages under `/admin` for a signed-in admin
  render inside the admin shell.
- `TenantMiddleware` merges every `Vary` response line and leaves a `Vary: *`
  response untouched (#423), and `tenant_source` is `None` whenever no tenant is
  bound (#424).
- Public pages no longer reload the whole document when a visitor clicks a link
  in authored content. A simple_module app is client-rendered — the root
  template ships `<div id="app"></div>` empty — so a navigation that creates a
  new document paints a blank white body until the bundle has booted. Admin
  screens were never affected because the shell navigates with Inertia's
  `<Link>`, but pagebuilder widgets and their markdown/rich-text fields render
  author-entered URLs as plain `<a href>`, and there is no component to swap for
  a `<Link>` when the anchor comes out of a markdown parser. A downstream site
  measured ~330ms of blank viewport per click on a throttled connection.
  `@simple-module-py/ui` now exports `startSpaLinkInterception()`, a delegated
  click handler that routes same-origin page links through Inertia whatever
  produced the anchor; the `smpy new` app template calls it. It deliberately
  leaves alone anything Inertia cannot render — other origins, non-http schemes,
  paths that look like a file, in-page anchors, `download`/`target`/
  `rel="external"`/`data-native-link`, and anchors inside a Puck editor surface
  — and falls back to a hard navigation if a visit returns without an
  `x-inertia` header, so a media download can never be replaced by an error
  modal. **Existing apps must add the one-line call to their own
  `host/client_app/app.tsx`**, which is scaffold output and so is not upgraded
  for them.
- `smpy gen-pages` now emits module stylesheet `@import` lines as **absolute
  paths** instead of `#module/<pkg>` alias specifiers. The alias only resolved
  if the host's `vite.config.ts` defined a matching `resolve.alias` — but that
  file is scaffold output, written into an app once and then owned and edited
  there, so it is versioned independently of these Python packages. Upgrading
  `simple_module_*` 0.0.26 → 0.0.27 therefore broke `vite build` in every app
  scaffolded earlier, failing with `Can't resolve '#module/<pkg>/styles.css'` —
  naming a specifier that appears nowhere in the app's own sources.

  `modules.generated.css` is now self-contained: it resolves under any
  `vite.config.ts`, with no alias configured at all, exactly as the `@source`
  lines in the same file already did. **No host action is required** — upgrade
  and re-run `gen-pages`. The scaffold template still defines the
  `#module/<pkg>` alias for hand-written imports, but nothing generated depends
  on it any more (GH issue #253).

### Added
- A module can now import another module's TS/TSX by npm package name:
  `import x from '@simple-module-py/pagebuilder/components/blockRegistry'`.
  Nothing in Node's own resolution made this work — a wheel-installed module is
  not an npm workspace member, so it never lands in `node_modules` at all;
  a workspace member *is* symlinked, but onto the source-tree module root, one
  level above the Python package, so subpaths landed somewhere nonexistent.

  `gen-pages` now records each module's `npm_name` in `modules.assets.json`,
  and the host aliases it onto the module's **Python package directory**. That
  anchor is forced, not chosen: a wheel ships `site-packages/<pkg>/**` and
  nothing above it, so the module root does not survive installation and the
  package directory is the only anchor both layouts share. The practical
  consequence is that the subpath is relative to the *package*:

  ```tsx
  import x from '@simple-module-py/foo/components/Widget';      // ✅ both layouts
  import x from '@simple-module-py/foo/foo/components/Widget';  // ❌ workspace-only
  ```

  If you previously hand-rolled this alias against the module root, drop the
  duplicated path segment. **Existing hosts need a `vite.config.ts` change** —
  unlike the CSS fix above, the import lives in module source rather than a
  generated file, so it cannot be made self-contained. In the loop over
  `modules.assets.json` entries, add:

  ```ts
  if (entry.npm_name) {
    moduleAliases.push({ find: entry.npm_name, replacement: entry.package });
  }
  ```

  and skip those names when collecting `optimizeDeps.include` — they resolve to
  source directories, not to pre-bundlable packages (GH issue #253).

## [0.0.27] — 2026-08-06

### Known issue
- Fixed in the `[Unreleased]` entry above. `gen-pages` emitted
  `@import "#module/<pkg>/…"` into `modules.generated.css`, which resolves only
  in hosts scaffolded at 0.0.27 or later; apps scaffolded earlier fail
  `vite build` after a Python-only upgrade. Either upgrade past this release,
  or add the alias to `host/client_app/vite.config.ts` by hand — build
  `{ find: '#module/' + package_name, replacement: package }` from each entry
  in `client_app/modules.assets.json` and pass the list as `resolve.alias`
  (GH issue #253).

## [0.0.16] — 2026-05-25

### Fixed
- The `users` module's post-login redirect (`login_redirect_url`) no longer
  hard-codes a `/` fallback when the Dashboard module isn't installed — `/`
  404s on apps without a root route (e.g. `smpy_gis`, `--preset minimal`). It
  now redirects to the first sibling module that exposes view routes, falling
  back to `/` only as an absolute last resort. Operator-set overrides are
  always preserved (GH issue #173).

## [0.0.15] — 2026-05-21

### Fixed
- The `moduleBareImportResolver` Vite plugin no longer short-circuits on
  `fsRoot`/`projectRoot` containment, so workspace-member modules at
  `modules/<name>/<pkg>/pages/` get the same workspace-root re-resolution as
  wheel-installed modules. In an npm-workspaces layout the workspace root *is*
  the resolver root, so the previous early-return excluded the very modules
  that need it. Cross-package bare imports (`maplibre-gl`, `pmtiles`, peer
  deps) now resolve in both wheel and workspace install modes (GH issue #156).
- The framework repo (Vite 8) seeds
  `optimizeDeps.rolldownOptions.resolve.modules` with the workspace
  `node_modules/` as a NODE_PATH-style fallback for the dep scanner
  (GH issue #155).

## [0.0.13] — 2026-05-15

### Fixed
- Vite's dev-mode dependency pre-bundling now resolves cross-package bare
  imports (e.g. `maplibre-gl`, `pmtiles`) from module pages whose importers sit
  outside the host's `client_app/`. The scaffold template (Vite 6) seeds
  `optimizeDeps.esbuildOptions.nodePaths` with the workspace `node_modules/`
  as a NODE_PATH-style fallback for the dep scanner (GH issue #152).

## [0.0.1] — 2026-04-21

Initial public release. All 12 Python packages publish to PyPI and all 3 JS packages publish to npm under the `@simple-module-py` scope.

### Python packages (PyPI)

- `simple_module_core`
- `simple_module_db`
- `simple_module_hosting`
- `simple_module_test`
- `simple_module_auth`
- `simple_module_background_tasks`
- `simple_module_dashboard`
- `simple_module_feature_flags`
- `simple_module_file_storage`
- `simple_module_permissions`
- `simple_module_settings`
- `simple_module_users`

### npm packages

- `@simple-module-py/ui`
- `@simple-module-py/i18n`
- `@simple-module-py/tsconfig`

### Added

- `smpy new <app>` CLI generator (shipped via the `simple_module_cli` PyPI distribution) scaffolding a working app with `users + dashboard + permissions` pre-wired.
- PyPI Trusted Publishing workflow (`.github/workflows/release.yml`) for zero-secret releases.
- npm Trusted Publishing for all three JS packages.

[Unreleased]: https://github.com/antosubash/simple_module_python/compare/v0.0.27...HEAD
[0.0.27]: https://github.com/antosubash/simple_module_python/compare/v0.0.26...v0.0.27
[0.0.16]: https://github.com/antosubash/simple_module_python/compare/v0.0.15...v0.0.16
[0.0.15]: https://github.com/antosubash/simple_module_python/compare/v0.0.14...v0.0.15
[0.0.13]: https://github.com/antosubash/simple_module_python/compare/v0.0.12...v0.0.13
[0.0.1]: https://github.com/antosubash/simple_module_python/releases/tag/v0.0.1
