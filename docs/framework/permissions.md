# Permissions

Permissions are **strings** owned by modules and enforced at endpoint boundaries. The framework doesn't know about specific permission strings — each module declares its own and attaches them to roles via the admin UI.

## Declaring permissions

Inside a module's `register_permissions(registry)`:

```python
from simple_module_core.permissions import PermissionRegistry

class OrdersModule(ModuleBase):
    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group("Orders", [
            "orders.view",
            "orders.create",
            "orders.edit",
            "orders.delete",
            "orders.export",
        ])
```

The group name (`"Orders"`) is the display label in the role editor. Permission strings conventionally use `<module>.<verb>` lowercase.

## Enforcing at endpoints

Use the `RequiresPermission` dependency from `simple_module_hosting.permissions`:

```python
from fastapi import APIRouter, Depends
from simple_module_hosting.permissions import RequiresPermission

router = APIRouter()

@router.post(
    "",
    status_code=201,
    dependencies=[Depends(RequiresPermission("orders.create"))],
)
async def create_order(...): ...

@router.get(
    "/export",
    dependencies=[
        Depends(RequiresPermission("orders.view")),
        Depends(RequiresPermission("orders.export")),
    ],
)
async def export_orders(...): ...
```

`RequiresPermission` raises `HTTPException(403)` if the current principal lacks the permission. Unauthenticated requests return 401 — the auth middleware runs earlier and attaches `request.state.principal`.

## Roles

Roles are named collections of permissions stored in the `users_role` table (owned by the `users` module). The mapping from role to permissions lives in `DEFAULT_ROLE_PERMISSIONS` (framework default) + per-role overrides in the DB.

```python
# simple_module_hosting.permissions
DEFAULT_ROLE_PERMISSIONS = {
    "admin": ["*"],
}
```

Host apps customize this by:

1. Editing roles in the admin UI at `/settings/permissions`.
2. Or seeding via code during `on_startup` in a custom host-level module.

The framework ships only `admin: ["*"]`. The wildcard grants every declared permission.

## Principal resolution

For each request, middleware resolves the current **principal** — a normalized user snapshot with expanded permissions — onto `request.state.principal`:

```python
@dataclass
class Principal:
    user_id: int | None
    email: str | None
    roles: list[str]
    permissions: set[str]
```

The `users` module owns the extraction from the session cookie. The framework's `InertiaLayoutDataMiddleware` reads `request.state.principal` and serializes `auth.user`, `auth.isAuthenticated`, `auth.permissions` into the Inertia shared props.

## Permission shorthand for menus

`MenuItem.required_permission` hides an item from users who don't have it. Evaluated in `InertiaLayoutDataMiddleware` *before* sending the menu to the client — the client never sees menu items it can't use.

```python
registry.add(MenuItem(
    section=MenuSection.SIDEBAR,
    key="orders",
    label_key="orders.menu.orders",
    href="/orders",
    required_permission="orders.view",
))
```

If you need a conjunction of permissions, use a comma-separated string (`"a,b"` means both) or a dedicated `required_any_of: list[str]` — see `simple_module_core.menu`.

## Client-side checks

The Inertia shared props include `auth.permissions`. Use them for UI affordances (hide/disable buttons), not for security:

```tsx
import { useAuth } from "@simple-module-py/ui";

export default function OrdersToolbar() {
  const { permissions } = useAuth();
  return (
    <div>
      {permissions.has("orders.create") && (
        <Button>Create order</Button>
      )}
    </div>
  );
}
```

**Security is enforced server-side.** A client-side check only hides the button; `RequiresPermission` on the POST endpoint prevents the actual creation.

## Testing with permissions

The `authenticated_client` fixture in `conftest.py` seeds an admin user (who has `*`). For tests that need a less-privileged user, build one from the `users` module fixtures or flip the principal temporarily:

```python
@pytest.mark.asyncio
async def test_create_requires_permission(client, db_session):
    # Create a user without `orders.create`
    from users.bootstrap import create_user
    user = await create_user(db_session, email="u@e.com", password="x")
    # Sign in via HTTP to get the session cookie
    r = await client.post(
        "/users/login", data={"email": "u@e.com", "password": "x"}
    )
    assert r.status_code in (200, 303)

    r = await client.post("/api/orders", json={...})
    assert r.status_code == 403
```

## Conventions

- **Namespace with the module name.** `orders.create`, not `create_order`.
- **Use `<module>.<verb>` form.** Nouns like `orders.admin` are fine for broad grants.
- **Don't inline string checks.** `if "orders.create" in principal.permissions: ...` scattered through code is hard to audit. Use `RequiresPermission` or refactor into a dependency.
- **Don't use roles in business logic.** Check permissions, not `principal.roles`. Roles are an admin concept; permissions are the enforcement boundary.
