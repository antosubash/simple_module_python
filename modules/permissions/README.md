# simple-module-permissions

Role-based access control (RBAC) for [simple_module](https://github.com/antosubash/simple_module_python) apps. Users get roles, roles carry permissions, and route handlers declare required permissions at the decorator or dependency layer.

Pre-wired into any app scaffolded with `simple-module new`.

## Install

```bash
pip install simple-module-permissions
```

## What it provides

- `Role` and `Permission` SQLModel tables, seeded from module-registered defaults.
- `@require_permission("orders.read")` route decorator and `HasPermission("...")` dependency.
- Admin UI at `/permissions/admin` for assigning roles to users.
- `register_permissions()` hook — every module declares its permission strings at boot, the registry dedupes and persists them.

## Usage

Declare permissions at module boot:

```python
# modules/orders/orders/module.py
class OrdersModule(ModuleBase):
    meta = ModuleMeta(name="orders")

    def register_permissions(self):
        return ["orders.read", "orders.write"]
```

Guard a route:

```python
from fastapi import APIRouter, Depends
from permissions.deps import HasPermission   # type: ignore[import-not-found]

router = APIRouter()


@router.get("/orders", dependencies=[Depends(HasPermission("orders.read"))])
async def list_orders(): ...
```

Admin flow: navigate to `/permissions/admin`, create a role, assign permissions, assign the role to users.

## Depends on

- `simple-module-core`, `simple-module-db`, `simple-module-hosting`, `simple-module-users`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
