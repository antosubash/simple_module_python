# Auth principal-resolver chain

**Status:** Approved, ready for implementation plan.
**Issue:** [#163 — simple_module_auth: expose a principal resolver that handles session cookie OR PAT bearer token](https://github.com/antosubash/simple_module_python/issues/163)
**Driver:** Unblock `smpy_gis` T3 (Personal Access Token workstream) by **end of M3 (2026-08-31)**.

## Problem

`smpy_gis` needs scripted, non-browser callers (CI jobs, GIS automation) to hit `/api/gis/*` using `Authorization: Bearer pat_xxx`. Today the only way to authenticate against `simple_module_python` is the session cookie set by `users.AuthMiddleware`; there is no extension point to plug in a second credential source.

Goal: a single `UserContext` arrives on `request.state.user` regardless of whether the caller authenticated with a session cookie or a bearer token. Every existing `get_current_user` / `require_permission` consumer keeps working without change.

Non-goal: shipping a PAT model, endpoints, or admin UI in upstream. Token storage is GIS-scoped (`gis_personal_access_tokens` table, per smpy_gis spec) and stays in the downstream module.

## Decision

Add a **principal-resolver chain** as an extension point owned by the `auth` module. Downstream modules register async resolvers in their `on_startup` hook; `users.AuthMiddleware` consults them after the session-cookie path fails.

Resolution order on every request:
1. **Session cookie** (existing fast path with `session["user_ctx"]` cache → DB fall-back).
2. **Registered resolvers**, in registration order, first non-`None` wins.
3. **Unauthenticated** → 401 JSON for `/api/*` paths, 302 to `/users/login` for view paths (with the original URL stashed in `session["next"]`).

Resolvers are request-scoped: they MUST NOT write to the session. A PAT call does not silently elevate to a long-lived session cookie.

## Architecture

### New types in `auth.contracts.resolver`

```python
from collections.abc import Awaitable, Callable
from starlette.requests import Request
from auth.contracts.schemas import UserContext

PrincipalResolver = Callable[[Request], Awaitable[UserContext | None]]
```

Documented invariants on every `PrincipalResolver`:
- Async; safe to call on every request (cheap bail when the credential type is absent — e.g., no `Authorization` header).
- Performs its own active/disabled checks before returning a `UserContext`.
- Returns `None` (never raises) for "credentials absent" or "credentials invalid"; the chain continues.
- Does not write to the session.

### New `auth.state.AuthState`

```python
from dataclasses import dataclass, field
from auth.contracts.resolver import PrincipalResolver


@dataclass
class AuthState:
    principal_resolvers: list[PrincipalResolver] = field(default_factory=list)
```

### `AuthModule.register_settings`

```python
def register_settings(self, app: FastAPI) -> None:
    from auth.state import AuthState

    app.state.auth = AuthState()
```

Module ordering: `UsersModule` already declares `depends_on=["Auth"]`. The framework runs `AuthModule.register_settings` before `UsersModule.register_middleware`, so `app.state.auth.principal_resolvers` is guaranteed to exist by the time `AuthMiddleware` reads it. Third-party modules that register resolvers also declare `depends_on=["Auth"]` and register in `on_startup`, which runs after every module's `register_*` hooks.

### `auth/__init__.py` re-exports

```python
from auth.contracts.resolver import PrincipalResolver
from auth.contracts.schemas import UserContext

__all__ = ["PrincipalResolver", "UserContext"]
```

So downstream authors do `from auth import PrincipalResolver, UserContext` without reaching into `contracts/`.

### `users.AuthMiddleware` changes

Two narrowly-scoped changes in `modules/users/users/middleware.py`:

**(1) Resolver fall-through.** After the existing session-cookie block, if `user_ctx is None`, iterate `app.state.auth.principal_resolvers`:

```python
if user_ctx is None:
    resolvers = getattr(scope["app"].state.auth, "principal_resolvers", ())
    if resolvers:
        request = Request(scope)
        for resolver in resolvers:
            try:
                user_ctx = await resolver(request)
            except Exception:
                logger.exception("Principal resolver %r raised; treating as no-match", resolver)
                continue
            if user_ctx is not None:
                break
```

**(2) 401 JSON for `/api/*` instead of redirect.** Replace the existing single-branch redirect with:

```python
if user_ctx is None and not is_public:
    if path.startswith("/api/"):
        response = JSONResponse({"detail": "Not authenticated"}, status_code=401)
    else:
        request = Request(scope)
        session[_SESSION_NEXT_KEY] = str(request.url)
        response = RedirectResponse(_LOGIN_REDIRECT, status_code=302)
    await response(scope, receive, send)
    return
```

Everything downstream of `user_ctx` resolution stays identical — the `current_user_id` ContextVar set/reset, `request.state.user = user_ctx` assignment, and the call to `self.app(...)` are unchanged. Resolvers populate the same `UserContext` shape the session path produces, so `TenantMiddleware`, `InertiaLayoutDataMiddleware`, audit listeners, and every `require_permission`-protected endpoint keep working with no edits.

## Behavior changes for existing deployments

There is one observable behavior change for session-only deployments: an unauthenticated XHR to a private `/api/*` route today returns `302 → /users/login` (HTML), and after this change returns `401 {"detail": "Not authenticated"}` (JSON). This is strictly better for scripted callers and for frontend XHR error handling; no existing test relies on the 302-for-API behavior (verified during exploration — the relevant tests in `modules/users/tests/test_users_middleware.py` cover view-route redirects).

No other change is visible to session-cookie users. The resolver chain is empty by default; the fall-through path is a no-op when no module registers a resolver.

## Public surface (apps build PAT resolvers against this)

```python
# In a downstream module's on_startup
from auth import PrincipalResolver, UserContext


async def my_pat_resolver(request: Request) -> UserContext | None:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        return None
    token = header.removeprefix("Bearer ")
    # Look up token in app's own storage, validate, load user + roles
    record = await my_token_store.find_active(token)
    if record is None:
        return None
    user = await my_user_loader.load(record.user_id)
    if user is None or not user.is_active or user.disabled_at is not None:
        return None
    return UserContext.from_user(user)


# in on_startup:
app.state.auth.principal_resolvers.append(my_pat_resolver)
```

## Testing

**`modules/auth/tests/test_resolver_registry.py`** (new):
- `AuthState()` initializes with empty `principal_resolvers`.
- `AuthModule().register_settings(app)` populates `app.state.auth` with an `AuthState` instance.
- Type-only smoke: a callable matching `PrincipalResolver` typechecks.

**`modules/users/tests/test_users_middleware.py`** (extend):
- Single resolver returns a `UserContext` → `request.state.user` is set, session keys unchanged.
- Two resolvers, first returns `None`, second returns context → second's context is used.
- All resolvers return `None` → unauthenticated path (redirect for view, 401 JSON for `/api/*`).
- Resolver raises → exception logged, chain continues to next resolver.
- `/api/private` unauthenticated → 401 JSON, no redirect.
- `/some-view` unauthenticated → 302 to `/users/login`, `session["next"]` set.
- Valid session cookie + registered resolver → session wins, resolver not called.

**`tests/test_principal_resolver_integration.py`** (new, repo root):
- Build an app with the standard fixtures plus a fake bearer-token resolver pointing at a test user.
- `Authorization: Bearer good` on a permission-protected endpoint → 200, principal honored.
- `Authorization: Bearer bad` → 401 JSON.
- No auth header → 401 JSON.
- Valid session cookie + `Bearer bad` → 200 via session; resolver chain not consulted.

No e2e changes — this is plumbing; the GIS app adds e2e for its own PAT flow.

## Documentation

- **`docs/framework/principal-resolvers.md`** (new, authoritative reference): the resolver contract, invariants, ordering, worked Bearer-token example, "when NOT to use a resolver".
- **`docs/framework-conventions.md`** (edit): one-paragraph pointer to the new doc under the existing auth section.
- `CLAUDE.md`: no change. The framework conventions doc + the new framework doc cover the surface.

## Out of scope

- PAT model, endpoints, or admin UI in upstream (GIS owns its `gis_personal_access_tokens` table and admin pages).
- LRU/in-memory caching of resolver results — resolvers are free to cache internally; the framework doesn't impose a strategy.
- Priority/ordering controls beyond registration order.
- Resolver-driven session writes (explicitly forbidden by the contract).
- Changes to OAuth or fastapi-users routers.
- Multi-tenant resolver shimming — resolvers populate `UserContext.tenant_id` themselves, and `TenantMiddleware` already consumes it.

## Acceptance (mirrors issue #163)

- `get_current_user` (and the underlying middleware) resolves session OR bearer in the documented order.
- Existing session-only consumers unaffected.
- Documented worked example in `docs/framework/principal-resolvers.md` shows an app adding a custom resolver.

## Timeline

- Implementation + tests + docs PR: needed in `main` by **end of M3 (2026-08-31)** so smpy_gis T3 can pick it up.
