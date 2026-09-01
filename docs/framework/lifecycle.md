# Lifecycle hooks

`ModuleBase` defines a set of lifecycle hooks. All are no-ops by default — override the ones you need.

At boot, for each module (in topological order), the framework calls them in this sequence:

```
register_settings
register_menu_items
register_permissions
register_feature_flags
register_event_handlers
register_health_checks
register_public_routes
register_csp_sources
register_design_packs
register_audit_links
register_exception_handlers
register_middleware
register_routes
register_admin_routes       (only when meta.admin_view_prefix is set)
-- on_startup (async, after middleware is installed)
```

On shutdown, `on_shutdown` runs in **reverse** dependency order.

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

## `register_event_handlers(bus, app=None)`

Subscribe to events on the in-process `EventBus`. Handlers can be sync or async; the bus awaits async ones.

```python
def register_event_handlers(self, bus: EventBus, app: FastAPI | None = None) -> None:
    from orders.contracts.events import OrderPlaced

    bus.subscribe(OrderPlaced, self._on_order_placed)


async def _on_order_placed(self, event: OrderPlaced) -> None: ...
```

Handlers are keyed by the exact event type and run concurrently on publish. See [Events](/framework/events).

`app` is optional. Take it when a handler needs `app.state.sm.db.session_factory` to persist on the framework's engine rather than building its own. The framework inspects your signature and calls the one-argument form `(self, bus)` when that is what you declared, so modules written before `app` existed keep working unchanged.

## `register_health_checks(registry)`

Register named async checks. They're surfaced at `/health/ready`:

```python
def register_health_checks(self, registry: HealthRegistry) -> None:
    registry.add(HealthCheck(name="orders.db", check=self._check_db))


async def _check_db(self) -> HealthCheckResult: ...
```

Each check returns a `HealthCheckResult(status=HealthStatus.HEALTHY | DEGRADED | UNHEALTHY, detail=...)`. The `/health/ready` endpoint runs all checks concurrently and reports the worst status (a raising check counts as `UNHEALTHY`).

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

Mount your API and Inertia view routers onto the two framework-provided routers.

```python
def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
    from orders.endpoints.api import router as api
    from orders.endpoints.views import router as views

    api_router.include_router(api)
    view_router.include_router(views)
```

- `api_router` is pre-built with `prefix=ModuleMeta.route_prefix`.
- `view_router` is pre-built with `prefix=ModuleMeta.view_prefix`.

The framework **auto-applies** `ModuleMeta.route_prefix` / `view_prefix` — `create_app` constructs each router already prefixed (`APIRouter(prefix=module.meta.route_prefix)`), so your `include_router` calls usually pass no further prefix (add one only for a sub-grouping *inside* the module's own prefix).

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
        AuditLink(
            entity_type=User.__name__,  # class name — NOT __tablename__
            url_template="/admin/users/{id}",
            label="User",
            label_key="users.audit.user",
        )
    )
```

`entity_type` matches `AuditEntry.entity_type`, which `snapshot_changes` writes as `type(obj).__name__`. Keying it off `__tablename__` (`"users_user"`) produces a link that never matches — and nothing errors: an unmatched lookup falls back to rendering `entity_type` as a plain label, so the row still shows text while silently never becoming a link. Using `Model.__name__` rather than a string literal makes a rename impossible to get wrong.

`url_template` must contain the literal `{id}` placeholder, substituted with the entity id. A template without it raises at boot rather than pointing every row at the same page.

`label_key` translates the label the same way `MenuItem.label_key` does, falling back to `label` when the key resolves to nothing. Rows are rendered server-side, so the audit view translates these before they reach the page.

The registry maps class names to URL templates and nothing more: it does not check that the row still exists or that the reader may open it. A link to a deleted record lands on the target screen's own 404, and permissions are enforced by the target route as usual.

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
        route_prefix="/api/orders",
        view_prefix="/orders",
        depends_on=["Users", "Products"],
        version="1.0.0",
    )

    def register_settings(self, app): ...
    def register_menu_items(self, registry): ...
    def register_permissions(self, registry): ...
    def register_feature_flags(self, registry): ...
    def register_event_handlers(self, bus, app=None): ...
    def register_health_checks(self, registry): ...
    def register_public_routes(self, registry): ...
    def register_csp_sources(self, registry): ...
    def register_exception_handlers(self, app): ...
    def register_middleware(self, app): ...
    def register_routes(self, api_router, view_router): ...

    async def on_startup(self, app): ...
    async def on_shutdown(self, app): ...
```

If your module overrides zero hooks, diagnostic `SM007` (INFO) asks whether the module is still doing anything useful. Empty modules are typically deletable.
