# Middleware pipeline

Starlette's `app.add_middleware(...)` is **LIFO**. The last middleware added is the **first** one executed on an incoming request (and the last to see the response on the way out). Keep this in mind — the order you see in `create_app` reads "inside out".

## Installation order (inside `create_app`)

The actual `add_middleware` call order (in `install_middleware`) is the
**reverse** of execution order, because the first added wraps innermost:

```python
# Added first → executed last (closest to the app)
app.add_middleware(InertiaLayoutDataMiddleware, ...)
app.add_middleware(LocaleMiddleware, ...)

if settings.multi_tenant:
    app.add_middleware(TenantMiddleware, ...)

for module in discovered_modules:
    module.register_middleware(app)  # each module may add 0+ middleware

app.add_middleware(SessionMiddleware, secret_key=...)
app.add_middleware(SecurityHeadersMiddleware, ...)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationIdMiddleware)
# Added last → executed first (outermost wrapper)
```

## Execution order (per request)

```
CorrelationId
  ↓
RequestLogging
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
app (route handler)
```

The response flows back up in the reverse of this order.

## What each built-in does

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

### `SecurityHeadersMiddleware`

Sets conservative defaults: `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: SAMEORIGIN`, `X-XSS-Protection: 0` (the legacy auditor is disabled in favour of CSP), plus a default CSP and — outside development — HSTS. In development the CSP is widened for the Vite dev origin and HSTS is suppressed. Override on a per-route basis with your own response headers.

### `SessionMiddleware`

Starlette's built-in signed-cookie sessions. Cookie name is `session`; attributes are `HttpOnly`, `SameSite=Lax`. `SameSite=Lax` is the CSRF defence: browsers don't attach the cookie to cross-site POST/PUT/DELETE, so a forged form submission from another origin is unauthenticated.

### `TenantMiddleware` *(opt-in)*

Resolves the tenant — first from the authenticated user's `tenant_id`, then (if the configured header is enabled, default name `X-Tenant-ID` via `SM_TENANT_HEADER`) from that request header — and sets both `request.state.tenant_id` and the `current_tenant_id` ContextVar. The `MultiTenantMixin` auto-filters SELECTs and auto-populates INSERTs using this value.

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

## Module middleware ordering

When two modules at the **same dependency tier** both call `app.add_middleware(...)` in their `register_middleware` hook, the framework invokes their hooks in topological order with a stable tiebreaker (module name). Because `add_middleware` is LIFO, the module that sorts **later** wraps its middleware **outermost** — so it runs **first** on the request.

Concretely, if modules `alpha` and `beta` both register middleware:

- `alpha` runs first (alphabetical tiebreaker, no `depends_on`).
- `beta.register_middleware` runs last, so its middleware is the outermost wrap.
- On a request: `beta.mw → alpha.mw → tenant → locale → app`.

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
