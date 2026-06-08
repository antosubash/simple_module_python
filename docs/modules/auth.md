# auth

A minimal public-API module. It owns the import paths every *other* module uses to read the current user (`UserContext`, `AuthProvider`, `get_current_user`, `require_permission`) and ships the provider-agnostic `AuthMiddleware` — but **no routes, no models, no UI**. The actual login/session logic lives in an auth-provider module ([`users`](/modules/users) for local accounts + OAuth, or [`keycloak`](/modules/keycloak) for Keycloak SSO).

Auth is **pluggable**: exactly one installed module registers an `AuthProvider` implementation on `app.state.auth.auth_provider`, and `AuthMiddleware` delegates to it on every request. The split exists so you can swap authentication backends without churning every consumer's import paths. Diagnostics enforce the invariant — `SM020` errors if two auth-provider modules are installed, `SM021` warns if none is.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Auth` |
| `route_prefix` | `/auth` |
| `view_prefix` | _(none)_ |
| `depends_on` | _(none)_ |

## Public contracts

```python
from auth.contracts import UserContext, AuthProvider
```

`UserContext` — a dataclass describing the authenticated user. Only set on `request.state.user` when a request is authenticated; downstream code reads it via `get_current_user` / `CurrentUser` (which 401 when it's absent). Fields:

| Field | Type | Notes |
|---|---|---|
| `id` | `str` | user id, stringified |
| `email` | `str` | |
| `name` | `str` | display name — `full_name or email` of the user |
| `roles` | `list[str]` | role names, e.g. `["admin"]` |
| `tenant_id` | `str \| None` | only set when multi-tenant |

Helpers: `has_role(role)` / `has_any_role(roles)` for in-handler role checks; `from_user(user)` builds a context from a duck-typed user object (`.id`, `.email`, `.full_name`, `.roles[*].name`, `.tenant_id`); `to_session_dict()` / `from_session_dict()` (de)serialise it into the signed session cookie.

`AuthProvider` is the `Protocol` an auth-provider module implements (`resolve_user`, `get_login_url`, `get_logout_url`, `get_public_paths`, `is_bearer_request`) — see [Pluggable auth](#pluggable-auth) below.

## Dependencies for endpoints

```python
from auth.deps import CurrentUser, get_current_user, require_permission
```

| Dependency | What it does |
|---|---|
| `CurrentUser` (`Annotated` alias) | FastAPI dependency that returns the active `UserContext`. Raises 401 if `request.state.user` isn't set. |
| `get_current_user(request, t)` | The underlying callable. Use this when you need to compose it manually. |
| `require_permission("orders.view", "orders.edit")` | Returns a dependency that passes if the user has **any** of the listed permissions, and 403s only if they have **none**. The `admin` role bypasses the check. |

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

## Pluggable auth

`AuthModule.register_settings` puts an empty `AuthState` on `app.state.auth` (holding `auth_provider` and `principal_resolvers`), and `register_middleware` installs `AuthMiddleware`. On each HTTP request the middleware:

1. Skips authentication for public paths — framework defaults (`/health`, `/static/`, `/api/docs`, `/api/redoc`, `/openapi.json`, `/i18n/`, and the exact path `/`), method-aware rules contributed via the [`register_public_routes`](/framework/lifecycle) hook (plus the `SM_AUTH_PUBLIC_PATHS` host escape hatch), and the provider's own `get_public_paths()` (prefix-only, kept for back-compat).
2. Calls `provider.resolve_user(request)` (the `AuthProvider` registered by `users` or `keycloak`).
3. On a miss, walks the **principal-resolver chain** (`app.state.auth.principal_resolvers`) in order — async callables `(Request) -> UserContext | None` for extra credential sources (PAT bearer tokens, API keys). The first non-`None` wins; each is wrapped in `try/except` so a raising resolver is treated as no-match.
4. If still unauthenticated and the path isn't public: returns `401` JSON for `/api/*` or bearer requests, otherwise stashes `next` in the session and redirects to `provider.get_login_url(request)`.

When a user is resolved it's written to `request.state.user` and the `current_user_id` ContextVar (for audit listeners).

Register an extra resolver from an app's `on_startup`:

```python
app.state.auth.principal_resolvers.append(my_pat_resolver)
```

## Locales

| Key | Default |
|---|---|
| `errors.not_authenticated` | `"Not authenticated"` |
| `errors.missing_permission` | `"Missing required permission: {permissions}"` |

Translated automatically when the request locale is set — no extra wiring needed.
