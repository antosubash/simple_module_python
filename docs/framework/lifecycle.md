# Lifecycle hooks

`ModuleBase` defines ten lifecycle hooks. All are no-ops by default — override the ones you need.

At boot, for each module (in topological order), the framework calls them in this sequence:

```
register_settings
register_menu_items
register_permissions
register_feature_flags
register_event_handlers
register_health_checks
register_exception_handlers
register_middleware
register_routes
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

Add entries to the global `MenuRegistry`. Items are grouped by `MenuSection` and role-filtered per request by `InertiaLayoutDataMiddleware`.

```python
def register_menu_items(self, registry: MenuRegistry) -> None:
    registry.add(MenuItem(
        section=MenuSection.SIDEBAR,
        key="orders",
        label_key="orders.menu.orders",     # i18n key
        href="/orders",
        icon="package",
        required_permission="orders.view",
        order=20,
    ))
```

`required_permission` filters the item from users without the permission. `order` is a stable sort key (lower = earlier).

Sections: `SIDEBAR`, `ADMIN_SIDEBAR`, `NAVBAR`, `USER_DROPDOWN`.

## `register_permissions(registry)`

Declare permission strings your module enforces. Grouped by a display name for the admin UI.

```python
def register_permissions(self, registry: PermissionRegistry) -> None:
    registry.add_group("Orders", [
        "orders.view", "orders.create", "orders.edit", "orders.delete",
    ])
```

Permissions become available in the role admin UI (`/settings/permissions`). See [Permissions](/framework/permissions).

## `register_feature_flags(registry)`

Declare feature flags with defaults. The admin can toggle them at `/settings/feature-flags`.

```python
def register_feature_flags(self, registry: FeatureFlagRegistry) -> None:
    registry.add("orders.new_checkout", default=False)
```

Query from code:

```python
flags = request.app.state.sm.feature_flags
if flags.is_enabled("orders.new_checkout", user=request.state.principal):
    ...
```

## `register_event_handlers(bus)`

Subscribe to events on the in-process `EventBus`. Handlers can be sync or async; the bus awaits async ones.

```python
def register_event_handlers(self, bus: EventBus) -> None:
    from orders.contracts.events import OrderPlaced
    bus.subscribe(OrderPlaced, self._on_order_placed)

async def _on_order_placed(self, event: OrderPlaced) -> None:
    ...
```

Dispatch walks the event's MRO, so subscribing to a base class delivers subclass events. See [Events](/framework/events).

## `register_health_checks(registry)`

Register named async checks. They're surfaced at `/admin/health`:

```python
def register_health_checks(self, registry: HealthRegistry) -> None:
    registry.add("orders.db", self._check_db)

async def _check_db(self) -> HealthStatus:
    ...
```

Return `HealthStatus.ok()` or `HealthStatus.failing(detail=...)`. The health endpoint aggregates all checks and returns 503 if any critical check fails.

## `register_exception_handlers(app)`

Register FastAPI exception handlers scoped to your module's exceptions:

```python
def register_exception_handlers(self, app: FastAPI) -> None:
    app.add_exception_handler(OrderNotFound, self._handle_not_found)

async def _handle_not_found(
    self, request: Request, exc: OrderNotFound
) -> Response:
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
def register_routes(
    self, api: APIRouter, views: APIRouter
) -> None:
    from orders.endpoints.api import router as api_router
    from orders.endpoints.views import router as view_router

    api.include_router(api_router, prefix="/api/orders")
    views.include_router(view_router, prefix="/orders")
```

- `api_router` is mounted at `/api` on the main app.
- `view_router` is mounted at `/` on the main app.

Prefixes in `ModuleMeta.route_prefix` / `view_prefix` are **documentation**; the framework does not auto-apply them. You specify the prefix in `include_router`.

## `on_startup()` / `on_shutdown()`

Async lifespan hooks that run after all modules are registered.

```python
async def on_startup(self) -> None:
    await self._worker_pool.start()

async def on_shutdown(self) -> None:
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
    def register_event_handlers(self, bus): ...
    def register_health_checks(self, registry): ...
    def register_exception_handlers(self, app): ...
    def register_middleware(self, app): ...
    def register_routes(self, api, views): ...

    async def on_startup(self): ...
    async def on_shutdown(self): ...
```

If your module overrides zero hooks, diagnostic `SM007` (INFO) asks whether the module is still doing anything useful. Empty modules are typically deletable.
