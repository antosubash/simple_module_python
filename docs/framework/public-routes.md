# Public routes (anonymous access)

`AuthMiddleware` (in `auth/middleware.py`) gates **every** request behind the
active auth provider — unauthenticated browser requests get a 302 to the login
URL, unauthenticated API requests get a 401. Modules that need to expose a
route without a session (a read-only STAC / OGC API, a TileJSON endpoint, an
inbound webhook, a status page) declare those routes through the
`register_public_routes` hook. The host collects every module's contributions
into one `PublicRouteRegistry` at boot, and the middleware consults it on every
request.

This is the supported alternative to the legacy `AuthProvider.get_public_paths`
contract, which is **prefix-only and method-agnostic** — it cannot express
"expose `GET /api/gis/datasets/{id}/tilejson` but keep `PATCH …/visibility`
authenticated" because read and write routes share a prefix.

## The hook

```python
from simple_module_core import ModuleBase, ModuleMeta, PublicRouteRegistry

class GisModule(ModuleBase):
    meta = ModuleMeta(name="Gis", route_prefix="/api/gis")

    def register_public_routes(self, registry: PublicRouteRegistry) -> None:
        # Whole read-only subtrees — any verb, any subpath.
        registry.add_prefix("/api/gis/stac")
        registry.add_prefix("/api/gis/ogc/")
        # A single anonymous search endpoint.
        registry.add_exact("/api/gis/catalog/search")
        # A GET read route nested under a mutation-bearing prefix: expose the
        # read, keep POST/PATCH siblings gated.
        registry.add_regex(r"/api/gis/datasets/[^/]+/tilejson$", methods={"GET"})
```

The hook runs once at boot, in dependency order, alongside the other
`register_*` registration hooks.

## Match kinds

A `PublicRoute` is **method-aware** and supports four match kinds. Every helper
takes an optional `methods=` set (case-insensitive); omitting it means *any*
verb matches.

| Helper | Matches when | Use for |
|---|---|---|
| `registry.add_prefix(p)` | `path.startswith(p)` | a whole read-only subtree |
| `registry.add_exact(p)` | `path == p` | a single endpoint |
| `registry.add_suffix(p)` | `path.endswith(p)` | a tail shared across resources |
| `registry.add_regex(p)` | `re.match(p, path)` (anchored at start) | a read route nested under a mutation prefix |

`registry.add(route_or_pattern, *, methods=, kind=)` is the general form;
pass a prebuilt `PublicRoute` or a string.

## Why method-awareness matters

`/api/gis/datasets/{id}/` carries both reads and mutations:

- `GET  /api/gis/datasets/{id}/tilejson`   — safe to expose anonymously
- `PATCH /api/gis/datasets/{id}/visibility` — must stay authenticated
- `POST  /api/gis/datasets/{id}/reprocess`  — must stay authenticated

A prefix rule would open all three. A method-scoped regex
(`methods={"GET"}`) exempts only the read, so the mutations keep returning 401
to anonymous callers.

## Resolution order

For each request, `AuthMiddleware` treats the path as public if **any** of:

1. **Framework defaults** — `/health`, `/static/`, `/api/docs`, `/api/redoc`,
   `/openapi.json`, `/i18n/`, the root `/`.
2. **`app.state.public_routes`** — the `PublicRouteRegistry` (module hooks +
   `SM_AUTH_PUBLIC_PATHS`). Method-aware.
3. **`provider.get_public_paths()`** — the auth provider's own login / register
   routes (legacy, prefix-only). Kept for back-compat.

A public path still resolves the user when a valid session is present (so a
public landing page can show "Open Dashboard" to a logged-in visitor) — it just
never *redirects* an anonymous caller away.

## Host-level escape hatch

When no module owns a route, an app can expose prefixes from the environment
without writing a module:

```bash
SM_AUTH_PUBLIC_PATHS='["/api/integrations/webhook", "/status"]'
```

These are seeded as prefix rules (method-agnostic). Prefer the
`register_public_routes` hook inside a module when you need method-awareness or
want the exemption to travel with the module that owns the route.

## Where it lives

- `PublicRoute` / `PublicRouteRegistry` — `simple_module_core.public_routes`
- The hook — `ModuleBase.register_public_routes`
- Wiring — `simple_module_hosting.app_builder.create_app` populates the
  registry and publishes it at `app.state.public_routes` (also
  `app.state.sm.public_routes`)
- Enforcement — `auth.middleware.AuthMiddleware`
