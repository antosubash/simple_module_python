# auth

A minimal public-API module. It owns the import paths every *other* module uses to read the current user (`UserContext`, `AuthProvider`, `get_current_user`, `require_permission`) and ships the provider-agnostic `AuthMiddleware` — but **no routes, no models, no UI**. The actual login/session logic lives in an auth-provider module ([`users`](/modules/users) for local accounts + OAuth, [`oidc`](/modules/oidc) for generic OIDC, or [`keycloak`](/modules/keycloak) for Keycloak SSO).

Auth is **pluggable**: exactly one installed module registers an `AuthProvider` implementation on `app.state.auth.auth_provider`, and `AuthMiddleware` delegates to it on every request. The split exists so you can swap authentication backends without churning every consumer's import paths. Diagnostics enforce the invariant — `SM020` errors if two auth-provider modules are installed, `SM021` warns if none is.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Auth` |
| `route_prefix` | `/auth` |
| `view_prefix` | _(none)_ |
| `depends_on` | _(none)_ |

## Shared OIDC helpers

`auth.oidc_common` holds the protocol pieces used by both `oidc` and
`keycloak`: the single-flight JWKS cache and RS256 validator, refresh-token
sealing and cookie-size guard, sign-in rotation and stale-state checks,
per-session refresh renewal with a 30-second transient-failure cooldown, race-safe cache
persistence with throttled activity writes, and the cache-backed directory.
It imports neither provider. Provider adapters retain their claim mapping,
endpoint configuration, session keys and identity rules. Keycloak identifies
cache rows by subject; OIDC uses issuer plus subject. Neither table changes
and no migration is needed (#741).

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
| `permissions` | `list[str]` | keys the principal carries itself (token scope / IdP claim), merged into the role-derived set by the resolver with `*` dropped; empty from `from_user`. Frozen in the session cookie like `roles` — revocable grants belong in a [grant source](/framework/permissions) |

Helpers: `has_role(role)` / `has_any_role(roles)` for in-handler role checks; `has_permission(key)` (exact match against `permissions` only — gate routes with `require_permission`, which also folds in roles and grant sources); `from_user(user)` builds a context from a duck-typed user object (`.id`, `.email`, `.full_name`, `.roles[*].name`, `.tenant_id`); `to_session_dict()` / `from_session_dict()` (de)serialise it into the signed session cookie (a cookie without `permissions` decodes to `[]`).

`AuthProvider` is the `Protocol` an auth-provider module implements (`resolve_user`, `get_login_url`, `get_logout_url`, `is_bearer_request`) — see [Pluggable auth](#pluggable-auth) below.

## Dependencies for endpoints

```python
from auth.web.deps import CurrentUser, get_current_user, require_permission
```

The old `auth.deps`, `auth.constants`, `auth.state` and `auth.middleware` import paths were removed in 0.0.46; import from `auth.web.deps`, `auth.core.*` and `auth.web.middleware`.

| Dependency | What it does |
|---|---|
| `CurrentUser` (`Annotated` alias) | FastAPI dependency that returns the active `UserContext`. Raises 401 if `request.state.user` isn't set. |
| `get_current_user(request, t)` | The underlying callable. Use this when you need to compose it manually. |
| `require_permission("orders.view", "orders.edit")` | Returns a dependency that passes if the user has **any** of the listed permissions, and 403s only if they have **none**. The `admin` role bypasses the check. |

## Example: protecting a route

```python
from fastapi import APIRouter, Depends
from auth.web.deps import CurrentUser, require_permission

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

`require_permission` passes when the user holds *any* of the listed keys. It reads the same per-request permission set as `simple_module_hosting.permissions.RequiresPermission`, which covers roles from the registry's role map plus every grant source (direct user grants, when the [permissions module](/modules/permissions#using-requirespermission) is installed).

## Pluggable auth

`AuthModule.register_settings` puts an empty `AuthState` on `app.state.auth` (holding `auth_provider` and `principal_resolvers`), and `register_middleware` installs `AuthMiddleware`. On each HTTP request the middleware:

1. Skips authentication for public paths — framework defaults: the exact paths `/`, `/health`, `/api/docs`, `/api/redoc` and `/api/openapi.json` (only when served), and everything under `/health/`, `/static/`, `/api/docs/`, `/api/redoc/` and `/i18n/` (a module route such as `/healthcare` is *not* public), method-aware rules contributed via the [`register_public_routes`](/framework/lifecycle) hook (plus the `SM_AUTH_PUBLIC_PATHS` host escape hatch), and, until 0.1.0, a third-party provider's deprecated `get_public_paths()` (prefix-only).
2. Calls `provider.resolve_user(request)` (the `AuthProvider` registered by `users`, `keycloak` or `oidc`).
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

### Browser session authority (#750)

OIDC and Keycloak stamp `oidc_authority`, a short SHA-256 hash of the provider
name, issuer and client ID, at sign-in. Cached principals and shared renewal
outcomes must match that authority; changing provider, issuer or client requires
sign-in again. No client secret is included. Anonymous login transactions remain
intact so state, nonce, PKCE and the saved destination survive authentication.

A cookie without the marker is upgraded only when it carries the selected
provider's own identity key (`oidc_identity` or `keycloak_identity`), or, for a
Keycloak cookie from before the identity key existed, its sealed
`keycloak_refresh_token`. OIDC also requires the recorded `oidc_identity`
issuer to match the discovered issuer used for ID-token validation (#764).
A different or unreadable issuer, or unavailable trusted discovery metadata,
clears the session and requires sign-in again. The same-issuer legacy cookie
is stamped and retained, including tenant-specific Entra issuers.
Other cached principals, including local users cookies, are cleared.
Legacy cookies do not record the old client ID, and Keycloak's sealed refresh
token does not expose a trusted old realm issuer. Rotate the host secret key
if you changed the client, or Keycloak issuer, before upgrading and must end
those unmarked sessions. No database migration is required.

### Concurrent browser renewal (#738)

Shared sign-in gives each browser session a random opaque `oidc_session_id`;
renewal preserves it. A framework lease serializes refresh grants across workers
(DB by default, Redis when configured): TTL 15 seconds, wait at most 3 seconds. Renewal work is bounded to 12 seconds
so token exchange and validation cannot outlive the lease.
The `auth_refresh_outcome` table shares the principal, new expiry and **sealed**
refresh token for 30 seconds; unrelated cookie fields are never copied. This
small DB store works with SQLite and Postgres without Redis; process-local TTL
caches and the invalidation bus cannot deliver these outcomes across workers.
Logout removes the session's shared outcome, so a replayed pre-rotation cookie
cannot adopt a renewed principal after sign-out (best effort; a failure never
blocks logout). Apply migration `a738c2e4f601` (`auth@head`) before upgrading.

Waiters adopt the outcome into their own cookie. A waiter whose outcome is gone,
or whose lease wait times out, leaves its cookie untouched (its copy still holds
the spent refresh token, and a late Set-Cookie must not overwrite the winner's);
that one request goes unauthenticated and the next uses the renewed cookie.
Unavailable coordination storage keeps the session with the normal 30-second
retry cooldown. Definitive provider rejections still clear authentication.
Expired outcomes are purged when a new outcome is published, so a lookup never
takes a write lock. An outcome is bound to the exact sealed refresh token being
spent: an older copy of the cookie cannot adopt it, while any holder of the same
pre-rotation cookie can within its 30 seconds (as that holder could also have
refreshed it first).
Existing cookies without an id coordinate their first renewal by a hash of their
sealed refresh token, then receive the winner's new random id. No plaintext
refresh tokens or identity tokens enter the outcome table.
