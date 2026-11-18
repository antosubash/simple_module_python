# Lifecycle hooks

`ModuleBase` defines a set of lifecycle hooks. Most are no-ops by default;
routes and locale files are discovered by package convention. Override only
what differs from those defaults.

At boot, the framework calls hooks in this sequence. Each phase visits modules
in topological order: settings first for all modules, then registrations per
module, then exception handlers, middleware and routes.

```
register_settings
register_menu_items
register_permissions
register_feature_flags
register_event_handlers
register_invalidations
register_health_checks
register_public_routes
register_body_limits
register_cors_policies
register_rate_limits
register_setup_steps
register_csp_sources
register_design_packs
register_audit_links
register_resource_types
register_principal_builder  (all modules, after database initialization)
register_exception_handlers
register_middleware
register_routes
register_admin_routes       (only when meta.admin_view_prefix is set)
-- framework routes, static/SPA mounts, host routers
register_fallback_routes    (all modules, in dependency order)
-- check_data_compatibility (async, before module settings hydration)
-- on_startup (async, after middleware is installed)
```

On shutdown, `on_shutdown` runs in **reverse** dependency order.

`register_principal_builder(registry)` installs app-free user-directory,
membership-role and persisted-role providers in a framework `PrincipalRegistry`.
The web host binds it to its session factory after database initialization;
workers call it alongside `register_permissions` using the same selected modules,
without running settings hooks or building an app. See
[principals outside requests](/framework/permissions#principals-outside-requests).

## `register_settings(app)`

**Called first.** Attach per-module state to `app.state.<module_lower>`. This is where your pydantic-settings object and any runtime-computed services go.

```python
def register_settings(self, app: FastAPI) -> None:
    from orders.settings import OrdersEnv
    from orders.state import OrdersState

    app.state.orders = OrdersState(settings=OrdersEnv())
```

If you override this hook but don't touch `app.state.<module_lower>`, diagnostic `SM012` warns in dev. See [Settings & app.state](/framework/settings).

## `register_menu_items(registry)`

Add entries to the global `MenuRegistry`. Items are grouped by `MenuSection` and filtered per request by `InertiaLayoutDataMiddleware` (by authentication state and `roles`).

```python
def register_menu_items(self, registry: MenuRegistry) -> None:
    registry.add(
        MenuItem(
            section=MenuSection.SIDEBAR,
            label="orders.menu.orders",  # i18n key, resolved client-side
            url="/orders",
            icon="package",
            roles=["admin"],  # empty = all authenticated users
            order=20,
        )
    )
```

`roles` filters the item to users holding at least one of the listed roles (empty list = visible to all authenticated users); `requires_auth` (default `True`) hides it from anonymous visitors. `order` is a stable sort key (lower = earlier).

Sections: `SIDEBAR`, `ADMIN_SIDEBAR`, `NAVBAR`, `USER_DROPDOWN`.

## `register_permissions(registry)`

Declare permission strings your module enforces. Grouped by a display name for the admin UI.

```python
def register_permissions(self, registry: PermissionRegistry) -> None:
    registry.add_group(
        "Orders",
        [
            "orders.view",
            "orders.create",
            "orders.edit",
            "orders.delete",
        ],
    )
```

Permissions become available in the role admin UI (`/admin/users/` (Roles tab)). See [Permissions](/framework/permissions).

## `register_feature_flags(registry)`

Declare feature flags with defaults. The admin can toggle them at `/admin/feature-flags/`.

```python
def register_feature_flags(self, registry: FeatureFlagRegistry) -> None:
    registry.add(
        FeatureFlagDefinition(
            name="orders.new_checkout",
            default_enabled=False,
        )
    )
```

Query from code:

```python
flags = request.app.state.sm.feature_flags
if flags.is_enabled("orders.new_checkout", tenant_id=request.state.tenant_id):
    ...
```

## `register_event_handlers(bus, app)`

Subscribe to events on the in-process `EventBus`. Handlers can be sync or async; the bus awaits async ones. The `app` argument is required: the host passes its app and workers pass `None`.

```python
def register_event_handlers(self, bus: EventBus, app: FastAPI | None) -> None:
    from orders.contracts.events import OrderPlaced

    bus.subscribe(OrderPlaced, self._on_order_placed)


async def _on_order_placed(self, event: OrderPlaced) -> None: ...
```

Handlers are keyed by the exact event type and run concurrently on publish. See [Events](/framework/events).

Use `app.state.sm.db.session_factory` when a handler needs to persist on the framework's engine. Subscribe durable handlers before returning early for `app is None`, so workers can deliver them.

## `register_invalidations(bus, app)`

Subscribe this module's per-process caches to the `InvalidationBus`, so another worker's write drops this worker's entry:

```python
def register_invalidations(self, bus: InvalidationBus, app: FastAPI) -> None:
    bus.subscribe("orders.totals", lambda inv: _TOTALS.pop(inv.key, None))
```

Handlers may be sync or async, and may only **forget** — the bus carries no delivery guarantee, so a handler that wrote to the database would do it an unknowable number of times. Publishing needs no hook: reach the same bus at `request.app.state.sm.invalidation` from a `db.on_commit` callback.

Whether an invalidation reaches other processes depends on a transport being installed (`background_tasks` installs a Redis one), so every cache keeps its TTL as a floor. See [Cache invalidation](/framework/invalidation).

## `register_health_checks(registry)`

Register named async checks. They're surfaced at `/health/ready`:

```python
def register_health_checks(self, registry: HealthRegistry) -> None:
    registry.add(HealthCheck(name="orders.db", check=self._check_db))


async def _check_db(self) -> HealthCheckResult: ...
```

Each check returns a `HealthCheckResult(status=HealthStatus.HEALTHY | DEGRADED | UNHEALTHY, detail=...)`. The `/health/ready` endpoint runs all checks concurrently, each with a 5 s deadline, and reports the worst status. A check that times out reports `UNHEALTHY` with detail `timed out`; a raising check reports `UNHEALTHY` with only the exception class name as detail (the endpoint is anonymous; the full error is logged at DEBUG, its class at WARNING).

## `register_body_limits(registry)`

Raise (or lower) the request-body ceiling for specific routes — the host
refuses any body over `max_request_body_bytes` (10 MiB by default) with a 413
before the route runs. A multipart upload endpoint declares what it needs:

```python
def register_body_limits(self, registry) -> None:
    registry.add_exact("/api/media/upload", 200 * 1024 * 1024, methods={"POST"})
```

See [request-guards.md](request-guards.md).

## `register_rate_limits(registry)`

Per-route rate limits for anonymous and signed-in requests, keyed by user, IP
or tenant: `registry.add_prefix("/api/x/", RateLimitRule("10/minute", key="user"))`.
See [request-guards.md](request-guards.md).

## `register_setup_steps(registry)`

Called after `register_rate_limits` and before `register_csp_sources`. Declare
what an install still needs before it is usable:

```python
from simple_module_core import SetupRegistry, SetupStep


def register_setup_steps(self, registry: SetupRegistry) -> None:
    registry.add(
        SetupStep(
            id="orders.catalog",
            title="Prepare the order catalog",
            title_key="orders.setup.catalog.title",
            is_complete=self._has_catalog,
            order=30,
        )
    )


async def _has_catalog(self, app: FastAPI) -> bool:
    return await app.state.orders.catalog_is_ready()
```

While any required step is incomplete, `SetupMiddleware` redirects to the
wizard at `/setup`. A step can provide a `SetupAction` to complete it in the
browser; its action runs only while that step is pending. Without an action,
the step must be completed out of band. Registering nothing opts out of the
gate. An action can supply `validate_before_migrations` to combine its form
with the preceding migration step on a never-migrated install: inputs are
validated before migrations, and the handler runs only if still pending
afterward. See [First-run setup steps](../module-authoring.md#first-run-setup-steps)
for action fields, translations and concurrency rules.

## `register_csp_sources(registry)`

Whitelist external origins your frontend loads assets from — a font CDN, a
tile server, an analytics endpoint. The host ships a strict
Content-Security-Policy; without a declaration the browser blocks the request.

```python
def register_csp_sources(self, registry) -> None:
    registry.add("style-src", "https://rsms.me")
    registry.add("font-src", "https://rsms.me")
```

Only fetch directives (`style-src`, `font-src`, `img-src`, `connect-src`, …)
can be extended — never `default-src`, `base-uri`, `form-action`, or
`frame-ancestors`, which belong to the host operator. Each source must be a
single origin/scheme token; invalid declarations raise at boot. The origins
land in both the development (Vite-widened) and production policies.

Production script directives use a per-request nonce and `strict-dynamic`.
In CSP3 browsers, script host allowlists are ignored: executable scripts in
custom templates must carry <code v-pre>nonce="{{ request.state.csp_nonce }}"</code>, including
external script entries. The Inertia adapter adds it to its module scripts;
imports loaded by those trusted entries inherit trust. Registered script
origins remain in the policy for older browsers; other asset directives
continue to use their allowlists. See [security headers](middleware.md#securityheadersmiddleware).

The hook runs before DB-backed settings are hydrated, so an origin that comes
from a setting can't be a static `add()`. Register a provider instead — it is
called on every response with the app and returns `(directive, source)` pairs:

```python
def register_csp_sources(self, registry) -> None:
    registry.add_provider(lambda app: [("img-src", app.state.maps.settings.tile_origin)])
```

Providers must be synchronous and read only in-memory state
(`app.state.<pkg>.settings`), never the database. Their pairs go through the
same validation as `add()`; a provider that raises, or an invalid pair, is
logged once and dropped — the static policy still applies. The finished policy
is cached by the pairs returned, so a settings edit takes effect on the next
response. With no providers the base policy is precomputed at boot; the request nonce
is inserted afterwards, outside the provider cache.

## `register_exception_handlers(app)`

Register FastAPI exception handlers scoped to your module's exceptions:

```python
def register_exception_handlers(self, app: FastAPI) -> None:
    app.add_exception_handler(OrderNotFound, self._handle_not_found)


async def _handle_not_found(self, request: Request, exc: OrderNotFound) -> Response:
    return JSONResponse({"detail": str(exc)}, status_code=404)
```

Handlers are registered on the main `app`, so they apply globally. Keep them tight to types your module owns.

## `register_middleware(app)`

Install ASGI middleware. Starlette's `add_middleware` is **LIFO** — the last middleware added runs first. Modules' middleware runs *between* the framework's built-in middleware and the app itself. See [Middleware pipeline](/framework/middleware) for ordering rules.

```python
def register_middleware(self, app: FastAPI) -> None:
    app.add_middleware(OrdersRateLimitMiddleware, rate=10)
```

When two modules at the same dependency tier both add middleware, the module that sorts **later** wraps outermost (executes first).

## `register_routes(api_router, view_router)`

By default this includes `<package>.web.endpoints.api.router` and
`<package>.web.endpoints.views.router` on the framework-provided routers.
Each endpoint module is optional. Discovery checks its exact module spec before
importing it: an absent module is skipped, but an import error inside an existing
module (or its parents) propagates and fails boot. An override replaces discovery.
For extra routers or custom ordering, override the hook:

```python
def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
    from orders.web.endpoints.api import router as api
    from orders.web.endpoints.extra import router as extra
    from orders.web.endpoints.views import router as views

    api_router.include_router(api)
    api_router.include_router(extra)
    view_router.include_router(views)
```

The host supplies tags and applies `ModuleMeta.route_prefix` / `view_prefix`
when mounting these routers. Do not repeat the prefixes in the hook. Both
prefixes default to `""`, preserving absolute paths registered by existing
modules. Declare prefixes explicitly in metadata, and retain existing values
when adopting conventional routers so URLs do not change.

## `register_fallback_routes(router)`

Use this opt-in hook for catch-all pages such as `/{slug}` or
`/{slug}/{page}`. It is a no-op by default: move catch-all routes out of the
conventional views router and include them here instead.

```python
def register_fallback_routes(self, router: APIRouter) -> None:
    from orders.web.endpoints.fallback import router as fallback

    router.include_router(fallback)
```

The host applies `ModuleMeta.view_prefix` once, just like ordinary views;
do not repeat it in the hook. Fallback routes are page routes, excluded from
OpenAPI and subject to the same API-token restrictions as ordinary views.
Auth and tenant middleware still run; CSRF dependencies remain opt-in.
Declare anonymous access through `register_public_routes` as usual. Avoid
broad public exemptions that would also exempt existing protected routes.

`create_app` calls this hook after every ordinary module and admin router,
framework route (including health, setup and admin), static/SPA mount and host
router. Pass host routers as `create_app(settings, routers=(host_router,))`,
or use `build_host_app(..., routers=(host_router,))`, which also accepts import
strings. Routers and mounts added to the returned app before startup or first
dispatch also stay ahead of fallbacks. The host finalizes ordering at lifespan
startup and before the first dispatch, including for clients that skip lifespan.
Finish composing the app before serving requests.

Fallback hooks run in the same topological dependency order as ordinary hooks,
after all ordinary routes are mounted. The first matching route wins, including
between fallback modules; use `depends_on` / `optional_depends_on` to express
ordering rather than relying on names. A handler returning 404 does not retry
later fallbacks. Static and SPA mounts likewise retain ownership of their
prefixes, including missing files. Bare mount prefixes redirect to the trailing
slash before fallbacks, preserving query strings and deployment `root_path`;
explicit ordinary routes at the bare prefix still win. Modules with only fallback
views retain their discovery order when choosing the default login destination.
No route-priority setting or host import of the fallback module is needed.

## `locale_dirs()`

The default discovers `<package>/locales` when it is a directory and returns
`{namespace: directory}`. The namespace uses the lowercase last component of the
Python package (`acme.billing` uses `billing`), independently of `ModuleMeta.name`.
A missing directory or a module without a package spec contributes nothing.
Override for a custom namespace/directory or return `{}` to opt out.

## `register_admin_routes(admin_router)`

A **second** view router, for modules that serve both public and admin pages and so cannot express both under one `view_prefix`. Called only when `ModuleMeta.admin_view_prefix` is set; the router arrives pre-built with that prefix.

```python
meta = ModuleMeta(
    name="Users",
    view_prefix="/users",  # sign-in, self-service
    admin_view_prefix="/admin/users",  # management CRUD
)


def register_admin_routes(self, admin_router: APIRouter) -> None:
    from users.admin.views import router as admin_views

    admin_router.include_router(admin_views)
```

A module gets exactly one view router, which is fine for a pure-admin module — it just points `view_prefix` at `/admin/...` and needs none of this. The second router exists for the cases where that doesn't work: `users` keeps `/users/login` public while its CRUD lives at `/admin/users`, and `dashboard` keeps `/dashboard/` while Doctor lives at `/admin/doctor`.

Both the field and the hook are additive and default to no-op, so a module written before they existed is unaffected.

> Putting a screen in the admin section means moving **three** things together: the URL (here), the menu registration (`MenuSection.ADMIN_SIDEBAR` in `register_menu_items`), and the layout the page renders in (`AdminLayout`). Change one and you get a page whose sidebar no longer lists it — a failure nothing about the diff makes obvious.

## `register_audit_links(registry)`

Teach the audit log how to link an entry back to the entity it describes, so a row reads as a link to the record rather than a bare type name.

```python
def register_audit_links(self, registry: AuditLinkRegistry) -> None:
    from users.models import User

    registry.register(
        AuditLink.for_model(
            User,  # fills entity_type=User.__name__ (NOT __tablename__) and table_name
            url_template="/admin/users/{id}",
            label="User",
            label_key="users.audit.user",
        )
    )
```

`entity_type` matches `AuditEntry.entity_type`, which `snapshot_changes` writes as `type(obj).__name__`. Keying it off `__tablename__` (`"users_user"`) produces a link that never matches — and nothing errors: an unmatched lookup falls back to rendering `entity_type` as a plain label, so the row still shows text while silently never becoming a link. `AuditLink.for_model(Model, ...)` fills `entity_type` from `Model.__name__` and `table_name` from `Model.__tablename__`, so a rename or a table-name mix-up is impossible; the plain `AuditLink(...)` constructor stays available for links without a model class.

`url_template` must contain the literal `{id}` placeholder, substituted with the entity id. A template without it raises at boot rather than pointing every row at the same page.

`label_key` translates the label the same way `MenuItem.label_key` does, falling back to `label` when the key resolves to nothing. Rows are rendered server-side, so the audit view translates these before they reach the page.

`label_resolver` names individual rows — a batch callable taking the request session and every id of that type on the page, returning `{id: display name}`. Only the owning module knows that a `Setting` is named by its key and a `User` by `full_name or email`, and without one the reader gets a bare primary key.

`label_permission` gates that name. **Set it whenever naming the row discloses something the module gates elsewhere.** The name travels inside the audit payload, so no downstream route ever gets the chance to refuse it — a reader holding `audit_log.view` and nothing else would otherwise read the display name (and, for accounts with an outstanding invite, the email) of every account that has ever been edited. `users` therefore declares `users.manage`. Readers without it still see the entry, the action and the id; they just do not get the name. Leaving it empty — the default — says the name is safe for anyone who may read the trail at all, which is true of setting keys, filenames and task names.

A link is a route, not an authorisation: apart from `label_permission`, the registry does not check that the row still exists or that the reader may open it. A link to a deleted record lands on the target screen's own 404, and permissions are enforced by the target route as usual.

## `register_resource_types(registry)`

Declare a resource type whose rows carry object-level access (owner, shares,
public), so cross-cutting code such as the `sharing` module can find its
policy and load a row by id. See [Resource-scoped access](./resource-access.md).

```python
def register_resource_types(self, registry: ResourceTypeRegistry) -> None:
    registry.register(
        ResourceType(name="notes.note", policy=NOTE_POLICY, select_by_id=select_by_id(Note))
    )
```

## `check_data_compatibility(db)`

This async read-only hook returns a sequence of `DataCompatibilityIssue` frozen
dataclasses (`upgrade_id`, `message`, `severity="warning"|"error"`, optional
`remediation_text`), empty by default.
Use stable semantic ids and inspect actual schema/data state so hosts with
independently ported revisions pass. Checks run before module DB-settings
hydration and `on_startup`; errors refuse boot outside development. A never-
migrated first run defers checks until migrations have been applied. Doctor
reports the same issues as `SM033`, through the same filtered sessions
(tenant and soft-delete rules in [Migrations](../database/migrations.md)).
Checks must never clear credentials or apply migrations.

Set `remediation_text` to give operators module-specific instructions. When
it is omitted and exactly one installed entry point registers the upgrade ID, the framework
suggests `smpy migrations prepare <upgrade-id> --head <host-head-or-label@head>`.

To ship a recipe, declare the upgrade ID in the `simple_module.data_upgrades`
entry-point group in the provider package's `pyproject.toml`.

```toml
[project.entry-points."simple_module.data_upgrades"]
"notes.upgrade_v1" = "notes.upgrades:upgrade_v1"
```

The target is a no-argument callable returning a `(branch_label, python_source)` tuple.
The UTF-8 Python source must be self-contained, define Alembic `upgrade()` and
`downgrade()` functions, and leave revision metadata for the CLI to append.
Keep upgrade IDs unique across installed packages. The CLI writes a host-owned
revision next to the selected `--head` revision, including when Alembic has
multiple `version_locations`. Review the generated revision before applying it.

## `on_startup()` / `on_shutdown()`

Async lifespan hooks that run after all modules are registered.

```python
async def on_startup(self, app: FastAPI) -> None:
    await self._worker_pool.start()


async def on_shutdown(self, app: FastAPI) -> None:
    await self._worker_pool.stop()
```

- `on_startup` runs in **topological** order.
- `on_shutdown` runs in **reverse** topological order.

Typical uses:

- Start Celery/RQ consumers (`background_tasks`).
- Warm caches.
- Register webhooks with external services.
- Probe required dependencies and fail boot on missing ones.

## Full example

```python
class OrdersModule(ModuleBase):
    meta = ModuleMeta(
        name="Orders",
        depends_on=["Users", "Products"],
    )

    def register_settings(self, app): ...
    def register_menu_items(self, registry): ...
    def register_permissions(self, registry): ...
    def register_feature_flags(self, registry): ...
    def register_event_handlers(self, bus, app): ...
    def register_invalidations(self, bus, app): ...
    def register_health_checks(self, registry): ...
    def register_public_routes(self, registry): ...
    def register_body_limits(self, registry): ...
    def register_cors_policies(self, registry): ...
    def register_rate_limits(self, registry): ...
    def register_setup_steps(self, registry): ...
    def register_csp_sources(self, registry): ...
    def register_design_packs(self, registry): ...
    def register_audit_links(self, registry): ...
    def register_resource_types(self, registry): ...
    def register_exception_handlers(self, app): ...
    def register_middleware(self, app): ...
    def register_admin_routes(self, admin_router): ...
    def register_fallback_routes(self, router): ...

    async def on_startup(self, app): ...
    async def on_shutdown(self, app): ...
```

During discovery, an omitted `ModuleMeta.version` resolves from the distribution
owning that entry point; explicit versions win. Discovery assigns new frozen
metadata to the instance without changing its class. Outside discovery, or without
an entry point distribution, the default remains `"1.0.0"`.

If your module overrides zero hooks and contributes no conventional routes or
locales, diagnostic `SM007` (INFO) asks whether it is still doing anything useful.
