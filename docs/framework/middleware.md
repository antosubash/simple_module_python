# Middleware pipeline

Starlette's `app.add_middleware(...)` is **LIFO**. The last middleware added is the **first** one executed on an incoming request (and the last to see the response on the way out). Keep this in mind — the order you see in `create_app` reads "inside out".

## Installation order (inside `create_app`)

The actual `add_middleware` call order (in `install_middleware`) is the
**reverse** of execution order, because the first added wraps innermost:

```python
# Added first → executed last (closest to the app)
app.add_middleware(CommitBeforeResponseMiddleware)
app.add_middleware(MaintenanceMiddleware)
app.add_middleware(InertiaCacheMiddleware)
app.add_middleware(InertiaLayoutDataMiddleware, ...)
app.add_middleware(LocaleMiddleware, ...)

if settings.multi_tenant:
    app.add_middleware(TenantMiddleware, ...)

for module in discovered_modules:
    module.register_middleware(app)  # each module may add 0+ middleware

app.add_middleware(SessionMiddleware, secret_key=...)
app.add_middleware(SecurityHeadersMiddleware, ...)
app.add_middleware(GZipMiddleware, minimum_size=...)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationIdMiddleware)

if settings.trusted_proxy:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=...)
# Added last → executed first (outermost wrapper)
```

## Execution order (per request)

```
ProxyHeaders                (only if SM_TRUSTED_PROXY is set)
  ↓
CorrelationId
  ↓
RequestLogging
  ↓
GZip
  ↓
SecurityHeaders
  ↓
Session
  ↓
<module middleware>        ← in whatever order each module installed them
  ↓
Tenant                      (only if SM_MULTI_TENANT=true)
  ↓
Locale
  ↓
InertiaLayoutData
  ↓
InertiaCache
  ↓
Maintenance
  ↓
CommitBeforeResponse
  ↓
app (route handler)
```

The response flows back up in the reverse of this order.

The last three are ordered relative to each other for reasons worth stating, because each is the kind of thing that looks arbitrary until it breaks:

- **`Maintenance` sits *inside* `InertiaCache`.** Its 503 is an Inertia payload produced by short-circuiting, carrying this user's auth block and menus like any other. Short-circuiting outside the cache guard would ship exactly the per-user payload that guard exists to keep out of caches. Because its `self.app` is the middleware below it, the 503 still travels back out through `InertiaCache`'s send-wrapper and picks up the same headers.
- **`Maintenance` runs *after* `InertiaLayoutData`, `Locale` and auth.** It needs the shared props to render with a layout instead of bare, the locale to answer in the right language, and the resolved user to know whether the caller is an admin who should pass through.
- **`CommitBeforeResponse` is innermost.** It hooks the `send` channel, so being added first makes its wrapper the first to see the response — which is what lets the commit land before any byte is written.

## What each built-in does

### `ProxyHeadersMiddleware` *(opt-in)*

uvicorn's own, installed **only** when `SM_TRUSTED_PROXY` is set — forwarded headers are never trusted by default. It sits outermost so the `X-Forwarded-*`-corrected scheme and client IP reach everything downstream: request logs record the real client rather than the proxy, and `request.url.scheme` reflects `X-Forwarded-Proto`.

Behind a TLS-terminating proxy this is **required**, not a nicety. Without it the app believes it is serving `http` while the browser is on `https`, Inertia's `pushState` sees a cross-scheme URL, throws a `SecurityError`, and login breaks.

Set it to a comma-separated list of proxy IPs/CIDRs, or `*` to trust any peer — correct when the container is only reachable through one proxy, wrong when anything else can connect.

### `CorrelationIdMiddleware`

Reads the `X-Correlation-ID` header (or generates a UUID4 hex) and makes the value available three ways:

- `request.state.correlation_id` — for handlers that already hold the `Request`.
- The `simple_module_hosting.logging.correlation_id` `ContextVar` — for code (services, background tasks spawned from a request) that doesn't.
- An `X-Correlation-ID` response header — so clients can cross-reference their request with server-side logs.

Every record emitted via the stdlib `logging` setup configured by `setup_logging()` already carries the ID under the `correlation_id` field, thanks to `_CorrelationIdFilter` reading the contextvar. For **structlog**, add a tiny processor that copies the framework's `ContextVar` into structlog's event dict:

```python
# anywhere during app startup (e.g. main.py)
import structlog
from simple_module_hosting.logging import correlation_id


def add_correlation_id(_, __, event_dict):
    cid = correlation_id.get("")
    if cid:
        event_dict.setdefault("correlation_id", cid)
    return event_dict


structlog.configure(
    processors=[
        add_correlation_id,
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
```

No per-handler `bind()` and no middleware of your own — the framework's middleware calls `correlation_id.set(...)` for the duration of every request, and the processor above lifts that value into every log event.

> `structlog.contextvars.merge_contextvars` is **not** a substitute here: it only merges `ContextVar`s whose names start with `structlog_` (set via `structlog.contextvars.bind_contextvars`), and the framework's `correlation_id` is a plain stdlib `ContextVar` outside that namespace.

### `RequestLoggingMiddleware`

Emits a structured log line per request with method, path, status, duration, and correlation ID. Respects `SM_LOG_FORMAT` (plain vs JSON) and `SM_LOG_LEVEL`.

### `GZipMiddleware`

Starlette's, compressing any response body over `COMPRESSION_MIN_BYTES` (500). Placed inside `CorrelationId` and `RequestLogging` — which set headers and read request state — but outside everything that produces a body, **including the `/static` mount**, which is where it earns its place: the built CSS is ~139 KB raw against ~21 KB gzipped, and the JS bundle compresses about 3×. Uncompressed assets dominated cold page load, several times larger than anything on the server request path.

### `SecurityHeadersMiddleware`

Sets conservative defaults: `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: SAMEORIGIN`, `X-XSS-Protection: 0` (the legacy auditor is disabled in favour of CSP), plus a default CSP and — outside development — HSTS. In development the CSP is widened for the Vite dev origin and HSTS is suppressed. Modules that load assets from an external origin extend the policy through the [`register_csp_sources`](lifecycle.md#register_csp_sourcesregistry) hook; both the dev and production variants honor those origins. Override on a per-route basis with your own response headers.

### `SessionMiddleware`

Starlette's built-in signed-cookie sessions. Cookie name is `session`; attributes are `HttpOnly`, `SameSite=Lax`. `SameSite=Lax` is the baseline CSRF defence: browsers don't attach the cookie to cross-site POST/PUT/DELETE, so a forged form submission from another origin is unauthenticated. Modules wanting defence in depth opt into the session-bound token check in `simple_module_hosting.csrf` — `RequiresCsrf` as a router dependency, `get_csrf_token(request)` exposed as a view prop, and callers echoing it as `X-CSRF-Token` on unsafe methods.

### `TenantMiddleware` *(opt-in)*

Resolves the tenant — first from the authenticated user's `tenant_id`, then from a request header if one is configured — and sets both `request.state.tenant_id` and the `current_tenant_id` ContextVar. The `MultiTenantMixin` auto-filters SELECTs and auto-populates INSERTs using this value.

Header lookup is **off unless you name a header**: `tenant_header` defaults to `""`, which the host passes through as `header=None`. `X-Tenant-ID` is the conventional name (exported as `TENANT_HEADER`) but is not a default — set `SM_TENANT_HEADER=X-Tenant-ID` to actually enable that path. Both this and `SM_MULTI_TENANT` are read from env at boot; see [Host settings](/reference/env-vars#host-settings-hostsettings) for why a DB edit cannot change them.

### `LocaleMiddleware`

Resolves the active locale in this order per request:
1. Cookie named by `SM_I18N_COOKIE_NAME` (validated against supported locales).
2. `Accept-Language` header with q-value parsing and longest-prefix match (`es-MX` → `es`).
3. `SM_I18N_DEFAULT_LOCALE`.

The resolved locale lands on `request.state.locale` and is used by `InertiaLayoutDataMiddleware` to pick the translation bundle for the shared props.

### `InertiaLayoutDataMiddleware`

Runs last (closest to the app). Populates `request.state.inertia_shared` with:

- `auth.user`, `auth.isAuthenticated`, `auth.permissions`
- `menus` — grouped by `MenuSection`, filtered by the current user's permissions
- `i18n` — `{ locale, bundle }` for the resolved locale

Inertia responses pick these up automatically via `InertiaDep` from `simple_module_hosting.inertia_deps`.

### `InertiaCacheMiddleware`

Keeps the Inertia payload out of caches that answer page requests.

Every Inertia route serves one URL as two representations, chosen on the request's `X-Inertia` header: an HTML document for a full page load, a JSON payload for a client-side visit. Nothing in either response says so, which leaves a cache free to store one and hand back the other — visit a page through the SPA, then open the same URL directly, and the browser can serve the stored payload as the document. The visitor gets `{"component":"...","props":{...}}` where the page should be.

That only bites once a route marks itself cacheable, which a public-content module reasonably does. What makes it unsafe is the framework: `InertiaLayoutDataMiddleware` merges the signed-in user's `auth` block, permission list and menus into **every** payload. A route author choosing `Cache-Control: public` for their own page content has no way to know that — which makes this a disclosure bug, not just a broken page — so the guarantee lives here rather than in each module:

- **An Inertia payload is never stored.** `Cache-Control: private, no-store`, and the ETag is dropped so no cache can revalidate its way back to a copy it should not have kept. The cost is per-visit caching on client-side navigation, which was never safe to take: those bytes are specific to one user.
- **Both representations declare `Vary: X-Inertia`**, so a cache that honours `Vary` keeps them in separate entries. `Vary` is added to the document only when the response is HTML, so static assets and JSON APIs keep the validators and cache entries they had.

A module that wants its public page content cached should give the **document** its own `Cache-Control` and an ETag. That path is left alone — this middleware only governs the payload.

The Inertia-request predicate mirrors `fastapi-inertia`'s own, which is presence-only (`"X-Inertia" in headers`), not an equality check against `true`. The two must agree: if the library renders JSON for `X-Inertia: 1` while this middleware doesn't recognise it as Inertia, the payload goes back marked however the route marked it — reopening the leak by changing one header value.

### `MaintenanceMiddleware`

Serves everyone but admins a 503 page while `maintenance_mode` is set on `HostSettings`. See [Maintenance mode](/reference/deployment#maintenance-mode) for operating it.

The flag is DB-backed rather than an env var on purpose: flipping it must not require a redeploy, which is exactly the moment you least want one.

Admins pass through — someone has to be able to reach the settings screen and switch it back off. For the same reason the auth provider's own routes stay open, so an admin who was signed *out* when the switch flipped can still sign in. Three prefixes stay reachable regardless: `/health` (so orchestrators don't kill the pod mid-maintenance), `/static/` and `/i18n/` (or the 503 renders unstyled and untranslated). Module routes registered through `register_public_routes` are honoured too, which is how branding's logo and favicon keep the maintenance page on-brand.

It **fails open** on missing config: a configuration gap taking the site down is the exact failure this feature would otherwise cause.

The middleware marks the request (`request.state.maintenance = True`) so the error page can tell a planned outage from the same status arriving unbidden. That matters most when the operator sets no message, which is the case where the page has nothing else to say.

### `CommitBeforeResponseMiddleware`

Finalizes the request's DB sessions at the ASGI `http.response.start` message — the last point still inside the request, late enough that response serialization has already run, early enough that a commit failure can still become a 500.

It exists because FastAPI runs a `yield` dependency's exit code *after* the response is delivered. `get_db` used to commit there, so a client that created a row and immediately read it back in a second request lost the race and got a deterministic 404 (GH #257).

Pure ASGI rather than `BaseHTTPMiddleware`, because the hook point is the `send` channel rather than the response object. `get_db` keeps the same commit in its own exit code as a fallback for when the middleware isn't in the stack; the session is claimed once, so whichever runs first wins.

> A request normally has exactly one session, since FastAPI caches the dependency. With several — `Depends(get_db, use_cache=False)` — a failure part-way through leaves the earlier commits durable while the client sees a 500. There is no cross-session atomicity to recover short of two-phase commit; the logged `db.session.commit_failed` is what makes it diagnosable.

## Module middleware ordering

When two modules at the **same dependency tier** both call `app.add_middleware(...)` in their `register_middleware` hook, the framework invokes their hooks in topological order with a stable tiebreaker (module name). Because `add_middleware` is LIFO, the module that sorts **later** wraps its middleware **outermost** — so it runs **first** on the request.

Concretely, if modules `alpha` and `beta` both register middleware:

- `alpha` runs first (alphabetical tiebreaker, no `depends_on`).
- `beta.register_middleware` runs last, so its middleware is the outermost wrap.
- On a request: `beta.mw → alpha.mw → tenant → locale → inertia → … → app`.

If you need a specific relative order, express it with `ModuleMeta.depends_on`. **Do not rely on names** — another module could be installed tomorrow that sorts differently.

## Writing a module middleware

Use the Starlette pattern. Keep it asynchronous.

```python
# modules/orders/orders/middleware.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class OrdersRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, rate: int = 10) -> None:
        super().__init__(app)
        self.rate = rate

    async def dispatch(self, request, call_next):
        # quick: consult request.app.state.sm.db / Redis for counters
        response = await call_next(request)
        response.headers["X-Orders-Rate-Limit"] = str(self.rate)
        return response
```

Register:

```python
# modules/orders/orders/module.py
def register_middleware(self, app: FastAPI) -> None:
    app.add_middleware(OrdersRateLimitMiddleware, rate=10)
```

## Patterns to avoid

**Reading request bodies.** Middleware that calls `await request.body()` consumes the stream; downstream handlers see an empty body. Use `ASGIApp` directly and replace the receive channel if you truly need this, or move the logic into a dependency.

**Mutating `app.state` per-request.** `app.state` is shared across requests. Use `request.state` for request-scoped data.

**Expensive setup per-request.** Middleware `__init__` runs once at installation; `dispatch` runs per request. Put constants in `__init__`.

**Ordering via naming tricks.** Prefixing modules with `aa_` to make them sort first works — until another dev copies the pattern and two modules collide. Use `depends_on` instead.
