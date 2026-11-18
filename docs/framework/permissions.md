# Permissions

Permissions are **strings** owned by modules and enforced at endpoint boundaries. The framework doesn't know about specific permission strings — each module declares its own and attaches them to roles via the admin UI.

## Declaring permissions

Declare a string enum catalogue in the module's constants, then attach it to
`ModuleBase.permissions`. The default `register_permissions` hook registers every
member; there is no repeated permission list:

```python
from simple_module_core import ModuleBase
from simple_module_core.permissions import PermissionCatalogue


class Permissions(PermissionCatalogue, group="Orders", label_key="orders.permission_group"):
    VIEW = "orders.view", "View orders"
    CREATE = "orders.create"
    EDIT = "orders.edit"
    DELETE = "orders.delete"


class OrdersModule(ModuleBase):
    permissions = Permissions
```

Members are strings: `RequiresPermission(Permissions.CREATE)`, menu guards, role
mappings and JSON use exactly `"orders.create"`. An optional `(key, label)` member
provides a human label in the role editor. `group` is the heading (defaults to
the catalogue class name); `label_key` translates that heading. Existing runtime
source labels take precedence over catalogue labels for the same key.

A custom `register_permissions` override calls `super().register_permissions(registry)`
to include its catalogue, then adds role mappings or runtime sources. Alternatively
call `registry.add_catalogue(Permissions)` explicitly. Existing `add_group`, `add`,
`PERM_*` string constants and overrides remain supported. Declaring a catalogue
registers keys only: it never grants roles or guards a route automatically.

Built-in modules declare their permissions through catalogues (#1037). Import
`Permissions` from a module's `core.constants` (file_storage retains its
`Permission` name). Imported legacy
`PERM_*` aliases are deprecated for removal in 0.0.50; stored permission keys and
role mappings are unchanged.

## Enforcing at endpoints

Use the `RequiresPermission` dependency from `simple_module_hosting.permissions`:

```python
from fastapi import APIRouter, Depends
from simple_module_hosting.permissions import RequiresPermission

router = APIRouter()

@router.post(
    "",
    status_code=201,
    dependencies=[Depends(RequiresPermission(Permissions.CREATE))],
)
async def create_order(...): ...

@router.get(
    "/export",
    dependencies=[
        Depends(RequiresPermission(Permissions.VIEW)),
        Depends(RequiresPermission(PERM_ORDERS_EXPORT)),
    ],
)
async def export_orders(...): ...
```

`RequiresPermission` raises `HTTPException(403)` if the current user lacks the permission. Unauthenticated requests return 401 — `AuthMiddleware` runs earlier and attaches `request.state.user` (a `UserContext`) plus the resolved permission set on `request.state.resolved_permissions`.

## Roles

Roles are named collections of permissions stored in the `users_role` table (owned by the `users` module). The mapping from role to permissions lives in `DEFAULT_ROLE_PERMISSIONS` (framework default) + per-role overrides in the DB.

```python
# simple_module_hosting.permissions
DEFAULT_ROLE_PERMISSIONS = {
    "admin": ["*"],
}
```

Host apps customize this by:

1. Editing roles in the admin UI at `/admin/users/` (Roles tab).
2. Or seeding via code during `on_startup` in a custom host-level module.

The framework ships only `admin: ["*"]`. The wildcard grants every declared permission.

## Principals outside requests

Use the caller's **async** database session to build a user's current account
principal, without constructing a request or a FastAPI app:

```python
from simple_module_db import principal_for

who = await principal_for(db, user_id, tenant_id)
if who is None:
    return  # unusable user/tenant, or nonmember without a platform wildcard
```

The result is a `ResourcePrincipal` (user id and resolved permission set), suitable
for `ResourcePolicy.filter`, `ResourcePolicy.can`, and `who.has(permission)`.
It checks the user directory with roles, validates membership in an active tenant,
adds only that membership's `tenant_role`, and merges code role mappings, persisted
role grants and direct grants. In multi-tenant mode a missing membership provider,
missing tenant, ordinary non-member or suspended tenant returns `None`. A platform
admin holding the wildcard may act without membership in an active tenant, matching
HTTP resource access on a public tenant subdomain; the registered `tenant_active`
provider validates that tenant through the caller's session (missing provider denies
this exception). Scoped credentials without the wildcard get no HTTP membership
bypass. With multi-tenancy off there is no membership check, and the host's
fixed `default_tenant` replaces the caller's tenant argument (unset stays unbound).
Missing users return `None`; missing registry configuration raises `RuntimeError`.
Directory/membership/role-store errors propagate rather than yielding a principal.
Grant-source failures retain the existing fail-closed behavior: log and contribute
no keys. Pending writes are flushed under the caller's original tenant before
lookup changes tenant context; nothing commits the session.

**Shared implementation.** `ModuleBase.register_principal_builder(registry)` is an
app-free registration hook. Users, Keycloak and OIDC supply a directory; Tenants
supplies active tenant and membership-role lookups; Permissions supplies persisted role
overlays and the session counterpart of its direct-grant source. The framework
imports no provider tables. The web host uses `get_user_directory(app)` and binds
the registry to its async session factory.

Requests and workers use separate loaders and the same pure `compose_principal`
function for the loaded account (including its membership role), role map and direct
grants. This preserves HTTP query counts: requests reuse the authenticated account,
Tenants' membership cache, Permissions' direct-grant TTL cache with singleflight,
and the role-overlay registry refreshed by invalidation (with periodic fallback).
They do not re-read those stores through the worker builder. Credential scope caps
and required permissions share the same composition. Workers read the caller's
session without these HTTP caches, so transaction-local changes are visible.

Request account and membership freshness follows the existing authentication and
membership cache invalidation/TTL rules. Losing a membership does not make a valid
account anonymous: global authenticated operations and tenant switching remain
available, while operations without an authorized tenant return 403. Unscoped
platform requests retain global permissions; a resource principal without an active
tenant on a multi-tenant host is anonymous.

The worker runner uses its merged host settings (env → DB → defaults), discovers
the same enabled modules and auth provider, and binds an independent registry to
each worker async session factory. It calls permission/principal registration
hooks, **not** settings/startup hooks, and builds no app. Persisted role overlays
and direct grants are read through the caller's session on each resolution, so
workers need no permission invalidation listener. Transaction-local role overlays
never mutate another session's registry. Custom factories can use
`build_principal_registry(modules, settings)` from `simple_module_core.principals`
and `bind_principal_registry(factory, registry)` from `simple_module_db.principals`;
pass the same selected, dependency-ordered modules as the host.

Eager tasks in the web process reuse the app's existing principal registry,
including its effective tenancy and provider selection. Reconfiguring or resetting
worker state replaces the registry on newly obtained worker session factories.

For a custom grant source, register
`registry.add_grant_source(request_source, session_source=session_source)` where the
counterpart is `async (db, user) -> keys`. HTTP resolution uses `request_source`;
worker resolution uses the session counterpart. Legacy sources without one receive
`request=None` in headless calls; they must handle it to contribute there. Neither source can grant `*`.

**External identity providers.** `DirectoryUser.roles is None` means unknown.
Keycloak/OIDC ID-only lookups cannot recover JWT/session roles, permissions or
current upstream account revocation from the local sign-in cache. They grant only
known tenant-role mappings and registered grant sources; never infer an admin role
or reuse an old token. Authenticated requests still honor their verified IdP claims,
so an ID-only lookup can intentionally have fewer permissions. Use an authoritative
directory provider if upstream activity/role parity is required without a token.

**Worker example** (multi-tenant host): use the existing worker loop and factory,
then bind the tenant around the resource query too. Principal construction restores
the previous tenant context; it does not scope queries made afterwards.

```python
from celery import shared_task
from background_tasks.outbox.loop import run_on_worker_loop
from background_tasks.outbox.worker import worker_session_factory
from simple_module_core.resources import ACTION_VIEW
from simple_module_db import principal_for, tenant_context
from sqlmodel import select


@shared_task(name="calendar.send_reminder")
def send_reminder(user_id: str, tenant_id: str, event_id: str):
    return run_on_worker_loop(lambda: _send_reminder(user_id, tenant_id, event_id))


async def _send_reminder(user_id, tenant_id, event_id):
    with tenant_context(tenant_id):
        async with worker_session_factory()() as db:
            who = await principal_for(db, user_id, tenant_id)
            if who is None:
                return
            stmt = CALENDAR_POLICY.filter(
                who, ACTION_VIEW, select(CalendarEvent).where(CalendarEvent.id == event_id)
            )
            event = (await db.execute(stmt)).scalar_one_or_none()
            if event is not None:
                await deliver_reminder(event, user_id)
```

**Token-feed example** (multi-tenant host): the module declares the GET path public
with `register_public_routes`. Its own token lookup must validate the token hash,
expiry and revocation, and return the stored owner and tenant. `principal_for` is an
authorization lookup, not a token authenticator; a user id supplied by a visitor
is never proof of identity. Keep the feed's scope limited to its calendar policy.

```python
from fastapi import Depends, HTTPException
from simple_module_core.resources import ACTION_VIEW
from simple_module_db import get_db, principal_for, tenant_context
from sqlmodel import select


@router.get("/calendar/feed")
async def token_feed(token: str, db=Depends(get_db)):
    credential = await lookup_valid_feed_token(db, token)
    if credential is None:
        raise HTTPException(404)
    with tenant_context(credential.tenant_id):
        who = await principal_for(db, credential.user_id, credential.tenant_id)
        if who is None or not who.has(PERM_CALENDAR_VIEW):
            raise HTTPException(404)
        stmt = CALENDAR_POLICY.filter(who, ACTION_VIEW, select(CalendarEvent))
        events = (await db.execute(stmt)).scalars().all()
        return render_calendar_feed(events)
```

## Delegated permission editing

User and role permission assignments are global. Delegated edits require
`permissions.manage` at the platform level and are bounded by platform-level
access: global roles, principal claims, and direct grants (including registered
grant sources), capped by API-token scopes. Synthetic `tenant:*` role mappings
do not contribute to this ceiling, even when the active tenant grants the same
permission. `resolve_principal_permissions(..., include_tenant_roles=False)`
resolves this ceiling without changing ordinary tenant-aware authorization or
the request's cached permissions. Credential validity still uses tenant-aware
permissions, so a token's required `api_tokens.use` may come from its tenant.

Delegated actors may add only keys within that ceiling and may edit only users
or roles whose existing permissions are within it. This also bounds retaining
or removing existing grants. Admin targets and users whose provider cannot
report their roles remain out of reach; unscoped platform admins remain
unrestricted. API refusals return 403; view writes redirect with a form error.

## Runtime permission sources

`register_permissions` runs before the database is open, so it cannot declare permissions for resources admins create later (per-record-type keys such as `records.product.edit`). Register a **source** instead:

```python
def register_permissions(self, registry: PermissionRegistry) -> None:
    registry.add_source("records", lambda: [("records.product.edit", "Edit products")])
```

The provider is **sync** and must read a module-maintained in-memory cache, because the registry is consulted on every request. It returns permission keys or `(key, label)` pairs. Its output is cached by the registry; call `registry.invalidate_source("records")` when the underlying resources change. Source permissions appear in `all_permissions`, in the role editor under the source's group name (labels ship in `PermissionGroupOut.labels`), in admin's implicit all-permissions, and are enforced by `RequiresPermission`. They are grantable and persisted like any other key. A source that raises is logged and contributes nothing.

## User resolution

For each request, `AuthMiddleware` resolves the authenticated user onto `request.state.user` as a `UserContext` (from `auth.contracts.schemas`):

```python
@dataclass
class UserContext:
    id: str
    email: str
    name: str
    roles: list[str] = field(default_factory=list)
    tenant_id: str | None = None
    permissions: list[str] = field(default_factory=list)
```

The active auth provider (`users`, `keycloak` or `oidc`) owns extraction from the session cookie / bearer token. `InertiaLayoutDataMiddleware` then expands roles into a permission set (cached on `request.state.resolved_permissions`) and serializes `auth.user`, `auth.isAuthenticated`, `auth.permissions` into the Inertia shared props. Permissions are derived mostly from roles via the `PermissionRegistry.role_map`. `UserContext.permissions` adds keys the principal carries itself — a token scope or IdP claim a provider or principal resolver maps in. `resolve_principal_permissions` (and so `RequiresPermission` and `auth.permissions`) merges them into the role-derived set, **dropping `*`**: like a grant source, a claim can never confer the wildcard; admin comes from roles only. Claim permissions stay in the signed session until the next sign-in, so revocable permissions belong in a grant source. HTTP resolution reuses the account validated by the authentication provider and its existing caches; worker lookups read local account roles and activity from the directory. Verified IdP claims remain request-only when directory roles are unknown. `UserContext.has_permission(key)` is an exact-match check against that list alone.

## Scoped principals (API tokens) and ungated routes

A principal with `UserContext.scopes` set — an [`api_tokens`](/modules/api_tokens)
personal access token or service key — has its permission set capped at those
scopes. Because the cap can only constrain a route that asks for a permission,
`simple_module_hosting.token_guard` (installed by `create_app` as an app-wide
dependency) applies a fail-closed rule to every route:

- a route whose dependency tree contains `RequiresPermission(...)` admits
  tokens — the gate decides;
- a page (a module view router, or any route depending on `InertiaDep`)
  refuses tokens with 403, gated or not;
- `Depends(TokenAllowed())` from `simple_module_hosting.token_guard` admits
  tokens explicitly, without a permission;
- `Depends(Authenticated())` marks "any signed-in user may call this" (401 with
  no principal). It satisfies diagnostic `SM031` and the OpenAPI export but is
  **not** a token opt-in: alone, a token is still refused; add `TokenAllowed()`
  to admit one too;
- every other route refuses tokens with 403 — except a public route, where the
  token's principal is dropped and the request runs anonymously (no user, no
  permissions, and the tenant an anonymous request would resolve to).

So **gate a route with a permission dependency if API tokens should reach it**;
a permission checked inline in the handler does not count. A gate passed as
`include_router(..., dependencies=[...])` counts: the guard reads the route as
FastAPI runs it (`scope["fastapi"]["effective_route_context"]`), include-level
dependencies included. Should a future FastAPI stop recording that context,
such a route falls back to failing closed (tokens refused), and a page still
refuses tokens through `page_route` itself. Sessions and a
provider's own bearer tokens (`auth_kind == "bearer"`) are unscoped and
unaffected. A custom gate dependency can mark itself with
`mark_token_gate(fn, GATE_PERMISSION)`.

## Role shorthand for menus

`MenuItem.roles` hides an item from users who hold none of the listed roles (an empty list = visible to all authenticated users); `requires_auth` (default `True`) hides it from anonymous visitors. Filtering happens in `MenuRegistry.get_for_user`, called by `InertiaLayoutDataMiddleware` *before* the menu reaches the client — so the client never sees menu items it can't use.

```python
registry.add(
    MenuItem(
        section=MenuSection.SIDEBAR,
        label="orders.menu.orders",
        url="/orders",
        roles=["admin"],
    )
)
```

Menu visibility is **role**-based (`MenuItem` has no `required_permission` field) — see `simple_module_core.menu`. Enforce the actual permission on the endpoint with `RequiresPermission`.

## Client-side checks

The Inertia shared props include `auth.permissions`. Use them for UI affordances (hide/disable buttons), not for security:

```tsx
import { usePermissions } from "@simple-module-py/ui/hooks/use-permissions";

export default function OrdersToolbar() {
  const { can } = usePermissions();
  return (
    <div>
      {can("orders.create") && (
        <Button>Create order</Button>
      )}
    </div>
  );
}
```

**Security is enforced server-side.** A client-side check only hides the button; `RequiresPermission` on the POST endpoint prevents the actual creation.

## Testing with permissions

The `authenticated_client` fixture from the `simple_module_test` plugin seeds an admin user (who has `*`). For tests that need a less-privileged user, build one from the `users` module fixtures or flip the principal temporarily:

```python
@pytest.mark.asyncio
async def test_create_requires_permission(client, db_session):
    # Create a user without `orders.create` (e.g. via the users
    # registration flow or by inserting a users.models.User row directly —
    # users.core.bootstrap only ships create_admin).
    ...
    # Sign in via the local-auth API to get the session cookie.
    r = await client.post("/api/users/auth/login", data={"username": "u@e.com", "password": "x"})
    assert r.status_code in (200, 204)

    r = await client.post("/api/orders", json={...})
    assert r.status_code == 403
```

## Conventions

- **Namespace with the module name.** `orders.create`, not `create_order`.
- **Use `<module>.<verb>` form.** Nouns like `orders.admin` are fine for broad grants.
- **Don't inline string checks.** `if "orders.create" in principal.permissions: ...` scattered through code is hard to audit. Use `RequiresPermission` or refactor into a dependency. When the thing to gate is part of a *response* rather than a route — a column, a label, a card — read the caller's grants with `resolved_permissions_for(request)` and test them with `simple_module_core.permissions.grants`, which is where the wildcard rule lives. A hand-rolled `in` check forgets that `admin` holds `*` and no named permission at all.
- **Don't use roles in business logic.** Check permissions, not `user.roles`. Roles are an admin concept; permissions are the enforcement boundary.
