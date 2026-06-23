# Principal-resolver chain

The `auth` module exposes an extension point — a list of async resolvers on
`app.state.auth.principal_resolvers` — that lets downstream modules plug in
additional credential sources alongside the built-in session cookie. This is
the supported way to add Personal Access Tokens, API keys, JWT bearers, or
any other request-scoped authentication scheme without forking
`auth.AuthMiddleware`.

## The contract

```python
from collections.abc import Awaitable, Callable
from starlette.requests import Request
from auth import PrincipalResolver, UserContext

PrincipalResolver = Callable[[Request], Awaitable[UserContext | None]]
```

A resolver MUST:

- Be **async** (it is awaited by the middleware).
- **Bail fast** when its credential type isn't present (e.g., return `None`
  immediately if there is no `Authorization` header) — resolvers run on
  every request, including completely unauthenticated ones.
- **Self-check active / disabled state** before returning a `UserContext`.
  The middleware does not re-validate.
- **Never raise** on bad credentials — return `None` so the chain continues
  to the next resolver. The middleware swallows exceptions defensively but
  resolver authors should not rely on it.
- **Not write to the session.** Resolver-authenticated requests are
  per-request only; they never silently elevate into a long-lived session
  cookie. (To mint a session, use the standard login flow.)

## Resolution order

`auth.AuthMiddleware` consults credential sources in this order:

1. **The active `AuthProvider`** — `provider.resolve_user(request)`, the
   existing fast/cached path (session cookie for the `users` provider). If it
   returns a `UserContext`, the user is authenticated and the resolver chain
   is **not** consulted.
2. **Registered resolvers**, in registration order. The first non-`None`
   return wins.
3. **Unauthenticated** — for `/api/*` paths (or any request the provider
   reports as a bearer request) the middleware returns
   `401 {"detail": "Not authenticated"}`; otherwise it 302-redirects to
   `provider.get_login_url(request)` (the `users` provider's is `/users/login`)
   and stashes the original URL in `session["next"]`.

The chain runs on **every** request, including public paths (`/health`,
`/openapi.json`, the login page itself). That lets a resolver attach
`request.state.user` for telemetry even on unauthenticated routes. The
unauthenticated response is suppressed for public paths regardless of
resolver outcome — the chain populates the principal, public-path
allow-listing controls the response.

## Worked example — bearer-token resolver

A module that ships its own Personal-Access-Token table registers a
resolver from its `on_startup` hook:

```python
# modules/example/example/module.py
from __future__ import annotations

from typing import TYPE_CHECKING

from auth import PrincipalResolver, UserContext
from simple_module_core.module import ModuleBase, ModuleMeta
from starlette.requests import Request

if TYPE_CHECKING:
    from fastapi import FastAPI


class ExampleModule(ModuleBase):
    meta = ModuleMeta(name="Example", depends_on=["Auth", "Users"])

    async def on_startup(self, app: FastAPI) -> None:
        app.state.auth.principal_resolvers.append(self._build_pat_resolver(app))

    @staticmethod
    def _build_pat_resolver(app: FastAPI) -> PrincipalResolver:
        async def resolve_pat(request: Request) -> UserContext | None:
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return None
            token = header.removeprefix("Bearer ")

            # Look up the token in the module's own storage and load the user.
            async with app.state.sm.db.session_factory() as session:
                record = await find_active_token(session, token)
                if record is None:
                    return None
                user = await load_user_with_roles(session, record.user_id)
                if user is None or not user.is_active or user.disabled_at is not None:
                    return None
                return UserContext.from_user(user)

        return resolve_pat
```

`depends_on=["Auth", "Users"]` ensures `AuthModule.register_settings` has
run (so `app.state.auth` exists) and — since `AuthModule.register_middleware`
installs `AuthMiddleware` (which calls the resolvers) — that the auth stack is
wired before this module's `on_startup` appends its resolver. The `Users`
dependency is for loading the user records the resolver looks up.

### Performance — caching the token lookup

The middleware does not cache resolver results (there's nothing safe to key
on — credentials must be re-validated every request to honor revocation).
For each authenticated request, the resolver opens a fresh DB session
and queries the token store. That's one round-trip per request.

For high-traffic deployments, cache the token-to-user mapping *inside*
the resolver — typically an LRU keyed by the token (or its hash) with a
short TTL. The resolver still runs every request, but the DB lookup is
skipped on cache hits. Pick a TTL short enough that revocation latency
stays acceptable. The framework deliberately stays out of this — caching
policy is a per-module concern.

## When NOT to write a resolver

- **You want to mint a long-lived session.** Use the standard login flow
  (`/users/login` or OAuth). Resolvers are explicitly forbidden from
  writing the session.
- **You only need a per-endpoint API-key check.** A FastAPI dependency
  (`require_api_key`) on the route signature is simpler and keeps the
  authenticated-user shape clean.
- **You want to override the `users` module's behavior** (e.g., reject
  active users, change role semantics). Resolvers add credential sources;
  they don't change the rules of authentication. For that, swap
  `UsersModule`/`AuthMiddleware` outright.

## Testing your resolver

Write resolver tests against a minimal app (see
`modules/users/tests/_middleware_support.py::_build_app` for the pattern
used by the framework's own resolver suite — it takes a
`principal_resolvers=` keyword and seeds `app.state.auth` for you).

End-to-end tests should drive the full `create_app(settings)` stack and
append your resolver to `app.state.auth.principal_resolvers` in a fixture —
see `tests/test_principal_resolver_integration.py` for a worked example.
