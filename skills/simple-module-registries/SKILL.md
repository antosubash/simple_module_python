---
name: simple-module-registries
description: Use when a module needs to contribute menu items, permissions, feature flags, or event handlers in a simple_module_python codebase — the four cross-cutting registries the framework gives every module. Triggers on "register_menu_items", "register_permissions", "register_feature_flags", "register_event_handlers", "MenuRegistry", "PermissionRegistry", "FeatureFlagRegistry", "EventBus", "feature_flag decorator", or "publish event".
---

# simple_module_python: cross-module registries

Four cross-cutting registries are populated during boot from each module's `register_*` hook. They turn the modular monolith into something more than a bag of routers: navigation aggregates, permission checks expand consistently, features can be toggled per tenant, and modules emit/consume events without importing each other.

All four are populated in **Phase 5** of `app_builder.build_app`, in this per-module order: `register_menu_items` → `register_permissions` → `register_feature_flags` → `register_event_handlers` → `register_health_checks` → `register_public_routes`. (The last two — health checks and anonymous-route exemptions — are also registries but out of scope here; see **simple-module-creating**.) Each is constructed once in Phase 3 and stashed on `app.state.sm` (as `menu_registry`, `permissions`, `feature_flags`, `event_bus`, …) only **after** all module hooks have run.

## Menu — `register_menu_items(registry: MenuRegistry)`

```python
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection


class OrdersModule(ModuleBase):
    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Orders",
                url="/orders/",
                icon="shopping-cart",
                order=10,
                section=MenuSection.SIDEBAR,
                roles=["admin", "staff"],  # empty list = all authenticated users
            )
        )
```

**Sections:** `SIDEBAR`, `ADMIN_SIDEBAR`, `NAVBAR`, `USER_DROPDOWN`. The `menus` shared prop on every Inertia response contains all four — the React layout chooses which to render where. `order` controls intra-section sorting (lower = first). `method="post"` is for items that need to be a form submission (logout) rather than a link. `group="Administration"` clusters items under a sub-header within a section; ungrouped (`""`) items render flat. `requires_auth=True` (default) hides the item from anonymous users.

## Permissions — `register_permissions(registry: PermissionRegistry)`

```python
from simple_module_core.permissions import PermissionRegistry


class OrdersModule(ModuleBase):
    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            "Orders",
            [
                "orders.view",
                "orders.create",
                "orders.delete",
            ],
        )
        registry.map_role("staff", ["orders.view", "orders.create"])
```

**Convention:** permission names are `<module>.<action>` (lowercase, dot-separated). Group name is human-readable — it surfaces in the admin UI as a section header. The built-in `admin` role gets the wildcard `"*"` and skips per-permission checks.

`register_permissions` runs once at boot to declare the static catalog. The registry caches its computed views (`all_permissions`, `role_map`) and **invalidates them on every mutation** (`add_group`, `add`, `map_role`), so it is safe to mutate after boot — the Permissions module does exactly that, re-applying persisted role→permission rows into `registry.map_role` at startup and whenever an admin edits a role. Don't roll your own caching of these views; read them fresh.

To check inside an endpoint, depend on `RequiresPermission("<module>.<action>")` (from `simple_module_hosting.permissions`), not by reading the registry by hand. The dependency handles wildcard expansion and the 401-vs-403 distinction.

## Feature flags — `register_feature_flags(registry: FeatureFlagRegistry)`

```python
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry


class OrdersModule(ModuleBase):
    def register_feature_flags(self, registry: FeatureFlagRegistry) -> None:
        registry.add(
            FeatureFlagDefinition(
                name="orders.bulk_import",
                description="Enables the CSV bulk-import UI on /orders/import",
                default_enabled=False,
            )
        )
```

**Resolution order at request time:** tenant override > system override > `default_enabled`. Per-tenant overrides come from the multi-tenant context (`request.state.tenant_id` from `TenantMiddleware`); system overrides come from the settings module's persisted overrides table.

**Checking a flag** (in an endpoint) — use the helper, not raw registry access:

```python
from simple_module_core.feature_flags import is_flag_enabled, require_flag, feature_flag

# Gate a whole endpoint (preferred — standard FastAPI, composes with dependencies=[]):
@router.post("/import", dependencies=[Depends(require_flag("orders.bulk_import"))])
async def bulk_import(...): ...

# Branch inside a handler:
@router.post("/import")
async def bulk_import(request: Request):
    if not is_flag_enabled(request, "orders.bulk_import"):
        raise HTTPException(404)
    ...

# Decorator alternative (legacy — kept for existing sites; new code should
# prefer Depends(require_flag(...))). Requires a `request: Request` param.
@router.post("/import")
@feature_flag("orders.bulk_import")
async def bulk_import(request: Request, ...): ...
```

Every helper accepts either the raw flag name or the `FeatureFlagDefinition` you registered, and reads `request.app.state.sm.feature_flags` + `request.state.tenant_id`, so the per-tenant override Just Works. `flag_enabled(flag)` is a dep factory yielding a `bool` when you need the value rather than a 404 gate.

## Events — `register_event_handlers(bus: EventBus, app: FastAPI | None = None)`

The event bus is async and in-process (backed by `pyee`'s `AsyncIOEventEmitter`). Modules emit + consume domain events without importing each other. The `app` parameter is optional and back-compat: override `register_event_handlers(self, bus, app=None)` when a handler needs `app.state.sm.db.session_factory` to persist on the framework engine (or `app.state.<module>` state) — the host passes `app` when your signature accepts it, otherwise calls the two-arg form.

```python
# orders/contracts/events.py
from dataclasses import dataclass
from simple_module_core.events import Event


@dataclass
class OrderPlaced(Event):
    order_id: int
    user_id: str
    total_cents: int
```

```python
# notifications/module.py
from simple_module_core.events import EventBus
from orders.contracts.events import OrderPlaced


class NotificationsModule(ModuleBase):
    def register_event_handlers(self, bus: EventBus, app: FastAPI | None = None) -> None:
        bus.subscribe(OrderPlaced, self._send_receipt)

    async def _send_receipt(self, event: OrderPlaced) -> None: ...
```

```python
# orders/service.py
async def place_order(self, ...):
    order = ...
    await self._bus.publish(OrderPlaced(order_id=order.id, ...))
    return order
```

**`publish`** awaits every handler concurrently via `asyncio.gather` and isolates handler failures (logged via `return_exceptions`, never propagated to the publisher). **`publish_nowait`** uses pyee's `emit` to schedule handlers as tasks on the running loop and returns immediately without awaiting them — use when the publisher must not block on handler latency. Both isolate handler errors; the difference is only whether the publisher waits.

The event bus has no persistence and no retry. If the host crashes between `publish` and the handler completing, the event is lost. For durable workflows use `background_tasks` (Celery) instead.

## Inter-module convention: contracts only

Module A consuming Module B's events should import only from `b.contracts.events`. Importing `b.service` or `b.models` couples them tightly and breaks the framework→plugin direction (`SM009`) when a framework piece accidentally pulls one of those imports along with it.

## Pitfalls

- **Added menu items or permission *groups* after boot.** The menu/permission/flag catalogs are meant to be declared in the `register_*` hooks. (The registries do invalidate their caches on mutation, so a late `add` won't serve stale data — but per-module hooks only run once at boot, so a catalog entry added later belongs to no module and won't survive a restart.) The one sanctioned runtime mutation is `PermissionRegistry.map_role`, which the Permissions module re-applies from the DB when an admin edits a role.
- **Raw permission strings in endpoints (`request.state.user.permissions`).** Use `RequiresPermission(...)`. The dependency handles wildcard expansion and the 401-vs-403 distinction.
- **Forgot a feature flag's `default_enabled=False`.** A flag added with `default_enabled=True` is on for every tenant on first deploy — defeats the point of gating a rollout. Default to `False`; flip via override after the rollout window.
- **Tried to subscribe to an event in `register_settings` instead of `register_event_handlers`.** `register_settings` receives only `app`, and `app.state.sm` (which holds `event_bus`) isn't assigned until **after** every registration hook runs — so the bus is unreachable there. Subscribe in `register_event_handlers`, which is handed the bus directly.
- **Used `publish_nowait` inside a request handler that needs the listener to commit a DB row in the same transaction.** It returns immediately — the handler runs after the request has already committed/rolled back. For "in this request, do X then Y", just call Y directly.

## Related skills

- **simple-module-creating** — where these hooks live in the lifecycle order
- **simple-module-conventions** — `SM009` (framework→plugin direction) applies to inter-module imports too
- **simple-module-doctor** — `SM007` fires when a module overrides no hooks at all
