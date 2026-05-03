# auth

A minimal public-API module. It owns the import paths every *other* module uses to read the current user (`UserContext`, `get_current_user`, `require_permission`) — but ships **no routes, no models, no UI**. The actual login/session/middleware logic lives in [`users`](/modules/users).

The split exists so you can swap out the users module (e.g. to plug in OAuth or LDAP) without churning every consumer's import paths.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Auth` |
| `route_prefix` | `/auth` |
| `view_prefix` | _(none)_ |
| `depends_on` | _(none)_ |

## Public contracts

```python
from auth.contracts.schemas import UserContext
```

`UserContext` — frozen-ish dataclass populated by the `AuthMiddleware` (in `users`). Fields:

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID \| None` | `None` for anonymous requests |
| `email` | `str` | empty string when anonymous |
| `full_name` | `str` | |
| `roles` | `list[str]` | role names, e.g. `["admin"]` |
| `tenant_id` | `str \| None` | only set when `SM_MULTI_TENANT=true` |
| `is_authenticated` | `bool` | property — `id is not None` |

It also exposes `to_session_dict()` / `from_session_dict()` for the middleware to (de)serialise itself into the session cookie.

## Dependencies for endpoints

```python
from auth.deps import CurrentUser, get_current_user, require_permission
```

| Dependency | What it does |
|---|---|
| `CurrentUser` (`Annotated` alias) | FastAPI dependency that returns the active `UserContext`. Raises 401 if `request.state.user` isn't set. |
| `get_current_user(request, t)` | The underlying callable. Use this when you need to compose it manually. |
| `require_permission("orders.view", "orders.edit")` | Returns a dependency that 403s if the user is missing **any** of the listed permissions. The `admin` role bypasses the check. |

## Example: protecting a route

```python
from fastapi import APIRouter, Depends
from auth.deps import CurrentUser, require_permission

router = APIRouter()

@router.get("/me")
async def me(user: CurrentUser) -> dict:
    return {"email": user.email, "roles": user.roles}

@router.delete(
    "/orders/{order_id}",
    dependencies=[Depends(require_permission("orders.delete"))],
)
async def delete_order(order_id: int, user: CurrentUser) -> None:
    # `user` is guaranteed authenticated here
    ...
```

For permission checks that need to honour **direct user grants** (not just role-derived perms), use [`RequiresPermission` from the permissions module](/modules/permissions#using-requirespermission) instead.

## Locales

| Key | Default |
|---|---|
| `errors.not_authenticated` | `"Not authenticated"` |
| `errors.missing_permission` | `"Missing required permission: {permissions}"` |

Translated automatically when the request locale is set — no extra wiring needed.
