# simple_module_permissions

Role-based access control (RBAC) for [simple_module](https://github.com/antosubash/simple_module_python) apps. Users get roles, roles carry permissions, and route handlers declare required permissions at the decorator or dependency layer.

Pre-wired into any app scaffolded with `smpy new`.

## Install

```bash
pip install simple_module_permissions
```

## What it provides

- `Role` and `Permission` SQLModel tables, seeded from module-registered defaults.
- `RequiresPermission("...")` FastAPI dependency that honours both role-based and direct user-level grants (the framework also exposes `require_permission(...)` from `auth.deps`).
- Admin UI for assigning roles/permissions to users, reached through the users admin area at `/users/admin`; role and user editors live at `/permissions/roles/{id}/edit` and `/permissions/users/{id}/edit`.
- `register_permissions(self, registry)` hook — every module declares its permission strings at boot via `registry.add_group(...)`; the registry dedupes and persists them.

## Usage

Declare permissions at module boot:

```python
# modules/orders/orders/module.py
from simple_module_core.permissions import PermissionRegistry


class OrdersModule(ModuleBase):
    meta = ModuleMeta(name="orders")

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group("Orders", ["orders.read", "orders.write"])
```

Guard a route:

```python
from fastapi import APIRouter, Depends
from permissions.deps import RequiresPermission   # type: ignore[import-not-found]

router = APIRouter()


@router.get("/orders", dependencies=[Depends(RequiresPermission("orders.read"))])
async def list_orders(): ...
```

Admin flow: navigate to `/users/admin`, create a role, assign permissions, assign the role to users.

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`, `simple_module_users`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
