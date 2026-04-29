---
name: simple-module-registries
description: Use when a module needs to contribute menu items, permissions, feature flags, or event handlers in a simple_module_python codebase — the four cross-cutting registries the framework gives every module. Triggers on "register_menu_items", "register_permissions", "register_feature_flags", "register_event_handlers", "MenuRegistry", "PermissionRegistry", "FeatureFlagRegistry", "EventBus", "feature_flag decorator", or "publish event".
---

# simple_module_python: cross-module registries

Four registries are populated during boot from each module's `register_*` hook. They turn the modular monolith into something more than a bag of routers: navigation aggregates, permission checks expand consistently, features can be toggled per tenant, and modules emit/consume events without importing each other.

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
                roles=["admin", "staff"],   # empty list = all authenticated users
            )
        )
```

**Sections:** `SIDEBAR`, `ADMIN_SIDEBAR`, `NAVBAR`, `USER_DROPDOWN`. The `menus` shared prop on every Inertia response contains all four — the React layout chooses which to render where. `order` controls intra-section sorting (lower = first). `method="post"` is for items that need to be a form submission (logout) rather than a link.

## Permissions — `register_permissions(registry: PermissionRegistry)`

```python
from simple_module_core.permissions import PermissionRegistry

class OrdersModule(ModuleBase):
    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group("Orders", [
            "orders.view",
            "orders.create",
            "orders.delete",
        ])
        registry.map_role("staff", ["orders.view", "orders.create"])
```

**Convention:** permission names are `<module>.<action>` (lowercase, dot-separated). Group name is human-readable — it surfaces in the admin UI as a section header. The built-in `admin` role gets the wildcard `"*"` and skips per-permission checks.

The runtime expansion (role → permissions) is cached. `register_permissions` is called once at boot; mutating the registry afterwards bypasses the cache and invalidates user sessions until the cache TTL elapses. Don't mutate at request time.

To check inside an endpoint, depend on the `RequireAnyPermissionDep` / `RequireAllPermissionsDep` dependencies (see auth/users), not by reading the registry by hand.

## Feature flags — `register_feature_flags(registry: FeatureFlagRegistry)`

```python
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry

class OrdersModule(ModuleBase):
    def register_feature_flags(self, registry: FeatureFlagRegistry) -> None:
        registry.add(FeatureFlagDefinition(
            name="orders.bulk_import",
            description="Enables the CSV bulk-import UI on /orders/import",
            default_enabled=False,
        ))
```

**Resolution order at request time:** tenant override > system override > `default_enabled`. Per-tenant overrides come from the multi-tenant context (`request.state.tenant_id` from `TenantMiddleware`); system overrides come from the settings module's persisted overrides table.

**Checking a flag** (in an endpoint) — use the helper, not raw registry access:

```python
from simple_module_core.feature_flags import is_flag_enabled, require_flag, feature_flag

@router.post("/import")
async def bulk_import(request: Request):
    if not is_flag_enabled(request, "orders.bulk_import"):
        raise HTTPException(404)
    ...

# Or as a decorator — 404 when off:
@router.post("/import")
@feature_flag("orders.bulk_import")
async def bulk_import(...): ...
```

All helpers read `request.state.tenant_id`, so the per-tenant override Just Works.

## Events — `register_event_handlers(bus: EventBus)`

The event bus is async and in-process. Modules emit + consume domain events without importing each other.

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
    def register_event_handlers(self, bus: EventBus) -> None:
        bus.subscribe(OrderPlaced, self._send_receipt)

    async def _send_receipt(self, event: OrderPlaced) -> None:
        ...
```

```python
# orders/service.py
async def place_order(self, ...):
    order = ...
    await self._bus.publish(OrderPlaced(order_id=order.id, ...))
    return order
```

**`publish`** awaits every handler concurrently via `asyncio.gather` and isolates handler failures (logged, not propagated). **`publish_nowait`** schedules dispatch on the running loop and returns immediately — use when the publisher must not be blocked or rolled back by handler failure.

The event bus has no persistence and no retry. If the host crashes between `publish` and the handler completing, the event is lost. For durable workflows use `background_tasks` (Celery) instead.

## Inter-module convention: contracts only

Module A consuming Module B's events should import only from `b.contracts.events`. Importing `b.service` or `b.models` couples them tightly and breaks the framework→plugin direction (`SM009`) when a framework piece accidentally pulls one of those imports along with it.

## Pitfalls

- **Mutated a registry after boot.** Boot-phase only. Cached views (menus, role→permission map) aren't invalidated for live requests; mutations look fine in dev with auto-reload and silently rot in prod.
- **Raw permission strings in endpoints (`request.state.user.permissions`).** Use `RequireAnyPermissionDep` / `RequireAllPermissionsDep`. The dependency handles wildcard expansion and 401 vs 403 distinction.
- **Forgot a feature flag's `default_enabled=False`.** A flag added with `default_enabled=True` is on for every tenant on first deploy — defeats the point of gating a rollout. Default to `False`; flip via override after the rollout window.
- **Subscribed to an event in `register_settings` instead of `register_event_handlers`.** `register_settings` runs **before** the event bus is constructed; the subscription silently no-ops.
- **Used `publish_nowait` inside a request handler that needs the listener to commit a DB row in the same transaction.** It returns immediately — the handler runs after the request has already committed/rolled back. For "in this request, do X then Y", just call Y directly.

## Related skills

- **simple-module-creating** — where these hooks live in the lifecycle order
- **simple-module-conventions** — `SM009` (framework→plugin direction) applies to inter-module imports too
- **simple-module-doctor** — `SM007` fires when a module overrides no hooks at all
