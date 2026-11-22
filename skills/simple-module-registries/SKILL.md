---
name: simple-module-registries
description: Use when a module needs to contribute menu items, permissions, feature flags, or event handlers in a simple_module_python codebase — the four cross-cutting registries the framework gives every module. Triggers on "register_menu_items", "register_permissions", "register_feature_flags", "register_event_handlers", "MenuRegistry", "PermissionRegistry", "FeatureFlagRegistry", "EventBus", "feature_flag decorator", or "publish event".
---

# simple_module_python: cross-module registries

Four cross-cutting registries are populated during boot from each module's `register_*` hook. They turn the modular monolith into something more than a bag of routers: navigation aggregates, permission checks expand consistently, features can be toggled per tenant, and modules emit/consume events without importing each other.

Registries are populated by `create_app` in dependency order. The complete hook
sequence is in `docs/framework/lifecycle.md`. The host's synchronous
`create_app(settings, customize=fn)` / `build_host_app(__file__, customize=fn)`
callback runs after all registration hooks, with `app.state.sm` available and
before the outer middleware pipeline is finalized. Apply host overrides there;
a module that sorts last still precedes later hook phases.

## Explicit host overrides (#954)

- Public routes: `app.state.sm.public_routes.remove(pattern, kind="exact", methods={"GET"})`.
  The literal registration pattern and kind must match. Omit methods to remove
  every scope; otherwise the complete normalized method set must match. All
  duplicates of that identity are removed; overlapping exemptions remain.
- Code grants: `app.state.sm.permissions.revoke_role(role, permission)` or
  `revoke_role(role)` for all grants from `map_role`. DB overlays are independent:
  they can grant the revoked permission only if they explicitly include it.
  Catalog sources, direct grants and the default admin wildcard are unchanged.
- Rate limits: `app.state.rate_limit_rules.replace_exact(path, rule)` (also
  `replace_prefix` / `replace_regex`). Rule methods override overlapping scopes
  for the same literal pattern, preserving other methods. Omit methods for all.
- Resources: `app.state.sm.resource_types.replace(resource_type)` validates and
  replaces by name. Plain `register` still rejects duplicate names.
- Events: `bus.unsubscribe(EventType, handler)`,
  `bus.unsubscribe_durable(EventType, name=NAME)` and
  `bus.replace_durable(EventType, replacement_handler, name=NAME)`. Stable names
  and SM034 semantics remain. Replacement also rebinds outstanding deliveries;
  removal does not delete outbox rows. Apply durable overrides to worker buses
  too: workers do not run the web host's callback.
- Shared props: `replace_inertia_shared_prop(app, key, provider)` from
  `simple_module_hosting`. The sync/async provider returns one value. Explicit
  replacement runs last and can replace framework keys; ordinary providers
  still keep the first key. Missing dynamic keys fail at render time.
- Middleware (#955): `replace_middleware(app, Target, Middleware(Subclass, ...))`
  from `simple_module_hosting`, in `customize`. The explicit Starlette object
  must name a subclass honoring the target's ASGI/security contract; constructor
  defaults and position are preserved. `disable_middleware(app, Target)` allows
  only GZip, RequestLogging and ServerTiming (compression/observability).
  Auth, Session, SecurityHeaders, BodyLimit, RateLimit and every other layer
  cannot be disabled. Missing or duplicate targets fail boot.

Module `register_middleware(self, app)` keeps its signature. Ordinary
`app.add_middleware` stays in the existing tier outside Tenant/Locale. Use
`simple_module_hosting.add_middleware(app, cls, stage="before_session")` for
transport work before Session, or `after="tenant"` / `stage="after_tenant"`
for tenant and locale context before layout permissions resolve. `stage="default"`
is the existing tier. Dependency order/LIFO applies within each stage. These
helpers must run in registration or `customize`, before assembly is finalized.
See `docs/framework/middleware.md` for replacement contracts and the stage table.

Missing removal/replacement targets raise `KeyError`. Plain additions preserve
existing accumulation, first-wins or duplicate rejection. Override existing
registry objects; do not replace `app.state.sm` or swap referenced registries.

## Menu — `register_menu_items(registry: MenuRegistry)`

```python
from simple_module_core.web.menu import MenuItem, MenuRegistry, MenuSection


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

`ModuleMeta(admin=AdminSurface(...))` supplies `ADMIN_SIDEBAR` and group defaults
for the owning module's menu URLs under its prefix, including provider items.
Explicit sections and nonempty groups/keys win. It also supplies page layout
and routing defaults; every route and menu item still declares its guards.

## Permissions — `register_permissions(registry: PermissionRegistry)`

Outside HTTP, use `await principal_for(db, user_id, tenant_id)` from
`simple_module_db`; never reconstruct a user's roles or membership from plugin
tables. Web and worker async sessions carry a `PrincipalRegistry` populated by
`register_principal_builder(registry)` (no app argument). Grant sources that read
the DB should register an app-free `session_source=async (db, user) -> keys` with
`add_grant_source`; session-owned lookups use this counterpart. HTTP resolution
keeps the request source and its caches; both loaders share pure composition.
Bind `tenant_context(tenant_id)` around subsequent resource queries. Unknown IdP
roles are not guessed outside a request. A platform wildcard bypasses membership
only in an active tenant, validated by the builder's session-owned `tenant_active`
provider; see `docs/framework/permissions.md`.

```python
from simple_module_core.access.permissions import PermissionCatalogue, PermissionRegistry


class Permissions(PermissionCatalogue, group="Orders", label_key="orders.permission_group"):
    VIEW = "orders.view", "View orders"
    CREATE = "orders.create"
    DELETE = "orders.delete"


class OrdersModule(ModuleBase):
    permissions = Permissions  # default hook registers every member

    def register_permissions(self, registry: PermissionRegistry) -> None:
        super().register_permissions(registry)
        registry.map_role(ROLE_STAFF, [Permissions.VIEW, Permissions.CREATE])
```

Catalogue members are strings used by guards and registration alike. Optional
member labels appear in the role editor; `label_key` translates the group.
Existing `PERM_*` constants, `add_group`, `add` and custom hooks stay supported.
No catalogue declaration grants a role or guards a route. Built-in modules use
`Permissions` from their `core.constants`; file_storage retains `Permission`.
Imported legacy `PERM_*` aliases are deprecated for removal in 0.0.50 (#1037).

Read role catalogs with `get_role_directory(app)` from `simple_module_core.access.role_directory`,
not provider tables. Its `editable` flag gates local assignment controls, while
role-name permission mappings work for Users, OIDC and Keycloak.

**Convention:** permission names are `<module>.<action>` (lowercase, dot-separated). Group name is human-readable — it surfaces in the admin UI as a section header. The built-in `admin` role gets the wildcard `"*"` and skips per-permission checks.

`register_permissions` runs once at boot to declare the static catalog. The registry caches its computed views (`all_permissions`, `role_map`) and **invalidates them on every mutation** (`add_group`, `add`, `map_role`, `revoke_role`, overlay updates), so it is safe to mutate after boot — the Permissions module uses separate role overlays for persisted grants at startup and whenever an admin edits a role. Don't roll your own caching of these views; read them fresh.

To check inside an endpoint, depend on `RequiresPermission(Permissions.VIEW)` (from `simple_module_hosting.permissions`), not by reading the registry by hand. The dependency handles wildcard expansion and the 401-vs-403 distinction.

## Feature flags — `register_feature_flags(registry: FeatureFlagRegistry)`

```python
from simple_module_core.web.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry


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
from simple_module_core.web.feature_flags import is_flag_enabled, require_flag, feature_flag

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

## Events — `register_event_handlers(bus: EventBus, app: FastAPI | None)`

The event bus is async and in-process (backed by `pyee`'s `AsyncIOEventEmitter`). Modules emit + consume domain events without importing each other. The `app` argument is required. The host passes its app; workers pass `None`. Use `app.state.sm.db.session_factory` when a handler needs the framework engine (or `app.state.<module>` state). Subscribe durable handlers before returning early when `app is None`.

```python
# orders/contracts/events.py
from dataclasses import dataclass
from simple_module_core.eventing.events import Event


@dataclass
class OrderPlaced(Event):
    order_id: int
    user_id: str
    total_cents: int
```

```python
# notifications/module.py
from simple_module_core.eventing.events import EventBus
from orders.contracts.events import OrderPlaced


class NotificationsModule(ModuleBase):
    def register_event_handlers(self, bus: EventBus, app: FastAPI | None) -> None:
        bus.subscribe(OrderPlaced, self._send_receipt)

    async def _send_receipt(self, event: OrderPlaced) -> None: ...
```

```python
# orders/web/service.py
async def place_order(self, ...):
    order = ...
    await self._bus.publish(OrderPlaced(order_id=order.id, ...))
    return order
```

**`publish`** awaits every handler concurrently via `asyncio.gather` and isolates handler failures (logged via `return_exceptions`, never propagated to the publisher). **`publish_nowait`** uses pyee's `emit` to schedule handlers as tasks on the running loop and returns immediately without awaiting them — use when the publisher must not block on handler latency. Both isolate handler errors; the difference is only whether the publisher waits.

The event bus has no persistence and no retry. If the host crashes between `publish` and the handler completing, the event is lost. For durable workflows use `subscribe_durable` and `publish_durable` with the outbox transport supplied by `background_tasks`.

## Inter-module convention: contracts only

Module A consuming Module B's events should import only from `b.contracts.events`. Importing `b.service` or `b.models` couples them tightly and breaks the framework→plugin direction (`SM009`) when a framework piece accidentally pulls one of those imports along with it.

## Pitfalls

- **Added menu items or permission *groups* after boot.** The menu/permission/flag catalogs are meant to be declared in the `register_*` hooks. (The registries do invalidate their caches on mutation, so a late `add` won't serve stale data — but per-module hooks only run once at boot, so a catalog entry added later belongs to no module and won't survive a restart.) The Permissions module refreshes persisted grants through role overlays; keep code mappings separate from DB grants.
- **Raw permission strings in endpoints (`request.state.user.permissions`).** Use `RequiresPermission(...)`. The dependency handles wildcard expansion and the 401-vs-403 distinction.
- **Forgot a feature flag's `default_enabled=False`.** A flag added with `default_enabled=True` is on for every tenant on first deploy — defeats the point of gating a rollout. Default to `False`; flip via override after the rollout window.
- **Tried to subscribe to an event in `register_settings` instead of `register_event_handlers`.** `register_settings` receives only `app`, and `app.state.sm` (which holds `event_bus`) isn't assigned until **after** every registration hook runs — so the bus is unreachable there. Subscribe in `register_event_handlers`, which is handed the bus directly.
- **Used `publish_nowait` inside a request handler that needs the listener to commit a DB row in the same transaction.** It returns immediately — the handler runs after the request has already committed/rolled back. For "in this request, do X then Y", just call Y directly.

## Related skills

- **simple-module-creating** — where these hooks live in the lifecycle order
- **simple-module-conventions** — `SM009` (framework→plugin direction) applies to inter-module imports too
- **simple-module-doctor** — `SM007` fires when a module overrides no hooks at all
