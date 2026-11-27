---
trigger: model_decision
description: Module discovery, layout, lifecycle hooks, middleware order, admin surfaces, Inertia, and CSRF rules for simple_module_python.
---

## Architecture

**Discovery.** Modules declare `[project.entry-points.simple_module]` pointing
at a `ModuleBase` subclass with `meta = ModuleMeta(...)`.
`simple_module_core.modules.discovery.discover_modules()` loads them, topologically sorts
by `ModuleMeta.depends_on` (plus `optional_depends_on`, ordering only, may be
absent), and the host calls each `register_*` hook in that order
(`docs/framework/discovery.md`). Outside development a missing `depends_on`
target fails the boot (`MissingDependencyError`, `SM030`); selecting
`keycloak` drops `Users`, so modules needing it must be left out.
Auth modules declare `ModuleMeta(provides_auth=True)` for selection and SM020;
the legacy `_is_auth_provider` marker warns once per class (removal 0.1.0).
Duplicate meta names raise `InvalidModuleError` (`SM008`) outside development,
naming both distributions; development warns and skips the later entry point.
Allowlists accept explicit `ep:<entry_point_name>` selectors as well as meta
names. Only lists containing solely explicit selectors skip other plugins before
import; unqualified names always match metadata and require loading candidates.
Unknown explicit selectors fail strict discovery and warn in development.
Entry points sort by distribution name, entry-point name and target before load,
making the development duplicate winner deterministic.

**Two names per module.** `ModuleMeta.name` (scaffold default: PascalCase,
`FeatureFlags`) keys Inertia render paths and `depends_on`; `SM_MODULES_ENABLED`
accepts this name or `ep:<entry_point_name>`, case-insensitively.
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
mirror `tests/<area>/<feature>/`, with no `__init__.py`, no top-level
`test_*.py`, and `conftest.py` at `tests/` root. Importlib mode allows repeated
basenames. JS tests stay in `tests-js/`.

**Framework layout.** Packages under `framework/` follow the same area layout
and `tests/<area>/` mirroring rules (`host/tests/test_framework_layout.py`,
`docs/framework-layout.md`). All seven framework packages follow this layout,
preserving top-level package exports and deprecated `sys.modules` alias shims
(`host/tests/test_deprecation_expiry.py`).

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
`register_admin_routes(admin_router)` (with `ModuleMeta.admin` or `admin_view_prefix`),
then `register_fallback_routes(router)` after framework routes, static/SPA mounts
and host routers (dependency order, first match wins; uses `view_prefix`),
then host `customize(app)` (`create_app` / `build_host_app`, with `app.state.sm`
available, before the outer middleware pipeline is finalized),
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
Catch-all views belong in `register_fallback_routes`, which defaults to no-op.
Pass host routers to `create_app(..., routers=...)` or `build_host_app(..., routers=...)`
so they precede fallbacks. Routes and mounts added to the returned app before
startup or first dispatch also stay ahead of fallbacks.

Rules that go with them:

- A module gets one view router per prefix. Declare `ModuleMeta(admin=AdminSurface(...))`
  for admin routing/menu/layout defaults. Legacy `admin_view_prefix` and
  `register_admin_routes` remain supported. Guard every route explicitly.
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
  (`simple_module_core.access.user_directory`), never `users.models` outside `users`.
  Read roles through `get_role_directory(app)` (`simple_module_core.access.role_directory`);
  `editable` describes local role assignment, not permission mapping edits.
  `DirectoryUser.roles is None` means unknown (Keycloak), not none. Recent
  activity: `get_activity_feed(app)`. `docs/framework/user-directory.md`.
- Menus: `MenuRegistry.add_provider(fn)` for per-request items; permissions:
  `PermissionRegistry.add_source(name, provider)` + `invalidate_source(name)`.
  `docs/framework/permissions.md`.

**Middleware** (Starlette `add_middleware` is LIFO). Execution order per
request: `(ForwardedHost if trusted proxy + allowlist) → (ProxyHeaders if
SM_TRUSTED_PROXY) → (SentryContext if Sentry is enabled) → CorrelationId →
RequestLogging → (ServerTiming, development only) → CORS → BodyLimit → GZip →
SecurityHeaders → <before_session> → Session → InertiaMiddleware → <default module middleware> →
(Tenant: multi_tenant, or fixed to default_tenant) → Locale → <after_tenant> → InertiaLayoutData →
RateLimit → Setup → Maintenance → CommitBeforeResponse → app`
(`framework/hosting/tests/pipeline/test_middleware_order.py` pins it). Rules that follow:

- Modules at the same dependency tier: the one that sorts later wraps outermost.
  Use `depends_on` to order, never names.
- `register_middleware(app)` keeps its signature. Use
  `simple_module_hosting.add_middleware(app, cls, stage="before_session"|"default"|"after_tenant")`
  or `after="tenant"` (inside both Tenant and Locale); ordinary
  `app.add_middleware` stays in the default tier. In `customize(app)`,
  `replace_middleware(app, Target, Middleware(Subclass, ...))` preserves the
  target's position and constructor defaults. Replacements must subclass the
  target and honor its security contract. `disable_middleware` permits only
  GZip, RequestLogging and ServerTiming; see `docs/framework/middleware.md`.
- Any `X-Inertia` response is forced `private, no-store`; to cache a public
  page, set `Cache-Control`/ETag on the *document* response only.
- `RateLimit` runs after auth, so by default it throttles only anonymous
  traffic to public routes. Per-route budgets: `register_rate_limits` rules
  (`RateLimitRule(rate, key="user"|"ip"|"user_or_ip"|"tenant")`) or the
  `RateLimit("10/minute", key="user")` dependency from
  `simple_module_hosting.rate_limit.rate_limit_deps`.
- Request bodies over `max_request_body_bytes` (10 MiB) are refused before any
  module sees them; per-path overrides via `register_body_limits`.
- CORS is opt-in per path (`register_cors_policies`, most specific match wins).
  `docs/framework/cors.md`.

Detail: `docs/framework/middleware.md`, `docs/framework/request-guards.md`.

**Admin section.** Prefer `ModuleMeta(admin=AdminSurface(prefix="/admin/<name>",
routes="<package>.admin.views:router", menu_group="Access",
menu_group_key="ui.nav_groups.access"))`. The base admin hook loads that router
(omitted target: `<package>.web.endpoints.admin:router`). This supplies the prefix,
`MenuSection.ADMIN_SIDEBAR`/group defaults for this module's menu URLs under it,
and `AdminLayout` for its pages without an explicit layout. `make gen-pages`
applies layouts through generated loaders, including in existing host resolvers.
Explicit menu sections, nonempty groups/keys and page layouts win. The surface
implies no permission: routes and menu items still declare their own guards.
Existing explicit wiring remains supported unchanged. `/admin` itself ships
with `simple_module_hosting`; `/api/*` paths never move.

**Inertia.** `inertia.render("<MetaName>/<Page>")` maps to
`modules/<pkg>/<pkg>/pages/<Page>.tsx`; host pages under
`host/client_app/pages/` use the bare name. Mismatches fire `SM003`/`SM004`.
Use `InertiaDep` from `simple_module_hosting.frontend.inertia_deps`; `InertiaResponse`
and prop factories (`optional`, `always`, `defer`, `merge`, `once`, `scroll`)
come from `simple_module_inertia`. Shared props `auth`, `menus`, `i18n` are set
by `InertiaLayoutDataMiddleware`; `auth.user` is null unless
`app.state.principal_serializer` is set (i18n caching via `X-SM-I18n`:
`docs/frontend/shared-props.md`). Inertia
`router.post/patch/put/delete` must target view routes, never `/api/*`
(`SM018`). Fast pages: `docs/frontend/performance.md` and the
`simple-module-page-perf` skill.

**CSRF.** Baseline is `SameSite=Lax` on the session cookie, so a same-site
request needs no token. For defence in depth, declare the `RequiresCsrf` router
dependency (`simple_module_hosting.auth.csrf`). Signed-in Inertia pages share the
current `csrfToken`, including partial reloads; the generated `api` client
echoes it as `X-CSRF-Token` on same-origin mutations. No per-page token props or
manual headers are needed. Anonymous auth forms explicitly expose their token.
The session cookie is `Secure` outside development and testing.
