# Middleware pipeline

Starlette's `app.add_middleware(...)` is **LIFO**. The last middleware added is the **first** one executed on an incoming request (and the last to see the response on the way out). Keep this in mind — the order you see in `create_app` reads "inside out".

## Installation order (inside `create_app`)

`create_app` installs the inner layers first and invokes each module's
`register_middleware(app)` hook in dependency order. Host `customize(app)` runs
with `app.state.sm` available, after all registration hooks. The framework then
installs the outer layers, inserts middleware assigned to named stages and
applies explicit replacements/disables. Starlette builds the ASGI stack on first
use. With no declarations, the existing middleware classes, options and execution
order are unchanged.

## Execution order (per request)

```
ForwardedHost               (only if SM_TRUSTED_PROXY and a forwarded-host allowlist are set)
  ↓
ProxyHeaders                (only if SM_TRUSTED_PROXY is set)
  ↓
SentryContext               (only if Sentry is enabled)
  ↓
CorrelationId
  ↓
RequestLogging
  ↓
ServerTiming                (development only)
  ↓
CORS                        (preflights answered here, before auth / rate limit)
  ↓
BodyLimit                   (413 on an oversized body)
  ↓
GZip
  ↓
SecurityHeaders
  ↓
<before_session module middleware>
  ↓
Session
  ↓
InertiaMiddleware           (303 / fragment 409 / empty-200 back / Vary / no-store)
  ↓
<default module middleware> (existing tier; includes Auth)
  ↓
Tenant                      (multi_tenant, or fixed to default_tenant)
  ↓
Locale
  ↓
<after_tenant module middleware>
  ↓
InertiaLayoutData
  ↓
RateLimit                   (429 for anonymous public-route traffic)
  ↓
Setup                       (first-run wizard takes precedence over maintenance)
  ↓
Maintenance
  ↓
CommitBeforeResponse
  ↓
app (route handler)
```

The response flows back up in the reverse of this order.

The last three are ordered relative to each other for reasons worth stating, because each is the kind of thing that looks arbitrary until it breaks:

- **`Maintenance` sits inside the adapter's `InertiaMiddleware`.** Its short-circuit responses receive the same cache protection and protocol normalization as page endpoints.
- **`Maintenance` runs *after* `InertiaLayoutData`, `Locale` and auth.** It needs the shared props to render with a layout instead of bare, the locale to answer in the right language, and the resolved user to know whether the caller is an admin who should pass through.
- **`CommitBeforeResponse` is innermost.** It hooks the `send` channel, so being added first makes its wrapper the first to see the response — which is what lets the commit land before any byte is written.

The two request guards, `BodyLimit` and `RateLimit`, are documented in [request-guards.md](request-guards.md): `BodyLimit` is early so a huge body never reaches GZip or any module, `RateLimit` is late because it needs the auth result and the shared props its error page renders with.

## What each built-in does

### `ProxyHeadersMiddleware` *(opt-in)*

uvicorn's own, installed **only** when `SM_TRUSTED_PROXY` is set — forwarded headers are never trusted by default. It sits outermost so the `X-Forwarded-*`-corrected scheme and client IP reach everything downstream: request logs record the real client rather than the proxy, and `request.url.scheme` reflects `X-Forwarded-Proto`.

Behind a TLS-terminating proxy this is **recommended**: without it the app believes it is serving `http` while the browser is on `https`, and every request log entry is attributed to the proxy's own address rather than the visitor's.

It used to be load-bearing for the UI too, because Inertia's page url was absolute and its cross-scheme `pushState` threw a `SecurityError` on every page (GH #223). The page url is root-relative now, so that failure mode is gone whether or not this is set.

It is still load-bearing for anything else that reads `request.url.scheme` or calls `request.url_for(...)` to build an absolute url — OAuth/OIDC's `callback_url` (`modules/users/users/oauth/api.py`, `modules/keycloak/keycloak/web/endpoints/api.py`) and the locale cookie's `secure` flag (`simple_module_hosting/i18n/i18n_routes.py`) among them. Left unset behind a TLS-terminating proxy, an OAuth redirect_uri is built as `http://…` and most providers reject it as a mismatch against the `https://…` one registered in their console.

Set it to a comma-separated list of proxy IPs/CIDRs (network addresses, such as `10.0.0.0/24`: a CIDR with host bits set trusts no peer and logs a WARNING), or `*` to trust any peer — correct when the container is only reachable through one proxy, wrong when anything else can connect.

### `ForwardedHostMiddleware` *(opt-in)*

Installed only when **both** `SM_TRUSTED_PROXY` and the `forwarded_host_allowlist` host setting (restart-required) are set. uvicorn's `ProxyHeadersMiddleware` fixes scheme and client but not the host, so behind a proxy that rewrites `Host`, `request.url_for(...)` and the tenants subdomain resolver see the upstream name. This middleware replaces the `host` header and `scope["server"]` with the rightmost `X-Forwarded-Host` value (the one the trusted proxy added) when the TCP peer is trusted (same `*` / IP / CIDR rule as uvicorn) **and** the value matches the allowlist: an exact host or `*.example.com` (any subdomain, never the apex), each with an optional `:port` (an entry without a port accepts any port). Anything else is ignored and logged at debug, so a forged header cannot poison absolute URLs. It is added after `ProxyHeaders` so it runs first and still sees the proxy's own address. `Forwarded:` (RFC 7239) is not supported. Email links are unaffected: they are built from configured base URLs (for example `tenants.public_base_url`), never from the request.

### `CorrelationIdMiddleware`

Reads the `X-Correlation-ID` header (or generates a UUID4 hex) and makes the value available three ways:

- `request.state.correlation_id` — for handlers that already hold the `Request`.
- The `simple_module_hosting.observability.logging.correlation_id` `ContextVar` — for code (services, background tasks spawned from a request) that doesn't.
- An `X-Correlation-ID` response header — so clients can cross-reference their request with server-side logs.

Every record emitted via the stdlib `logging` setup configured by `setup_logging()` already carries the ID under the `correlation_id` field, thanks to `_CorrelationIdFilter` reading the contextvar. For **structlog**, add a tiny processor that copies the framework's `ContextVar` into structlog's event dict:

```python
# anywhere during app startup (e.g. main.py)
import structlog
from simple_module_hosting.observability.logging import correlation_id


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

It runs at `COMPRESSION_LEVEL` 5, not Starlette's default of 9. Compression runs on the event loop that serves every other request, and level 9 buys almost nothing on JSON and HTML: a 76 KB first-load page comes out 1.2% smaller than at level 5 for 2.4× the CPU (6.4 ms vs 2.7 ms). Pre-compressed static assets are served as-is and never re-compressed, so they keep whatever level they were built with.

### `SecurityHeadersMiddleware`

Sets conservative defaults: `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: SAMEORIGIN`, `X-XSS-Protection: 0` (the legacy auditor is disabled in favour of CSP), plus a default CSP and — outside development — HSTS. In development the CSP is widened for the Vite dev origin and HSTS is suppressed. Modules that load assets from an external origin extend the policy through the [`register_csp_sources`](lifecycle.md#register_csp_sourcesregistry) hook; both the dev and production variants include those origins.

Outside development, `script-src` and `script-src-elem` use
`'self' 'nonce-<request nonce>' 'strict-dynamic'`, without `'unsafe-inline'` or
`'unsafe-eval'`; `script-src` additionally allows `'wasm-unsafe-eval'` so
WebAssembly can compile without re-enabling JavaScript `eval`. A `304 Not
Modified` carries no CSP header, so the cached document keeps the policy whose
nonce matches its body; for the same reason a nonce-bearing document must not
be stored by a shared cache (`Cache-Control: public`), which would replay one
nonce to every visitor. Each HTTP request gets `request.state.csp_nonce`. The host's
pre-paint script and Inertia's module entry carry that nonce; custom templates
must put <code v-pre>nonce="{{ request.state.csp_nonce }}"</code> on every executable script,
including external entries. JSON page data and JSON-LD are inert and need no
nonce. Development retains the permissive Vite/HMR policy.

CSP3 browsers ignore script host allowlists under `strict-dynamic`; a nonced
entry can load its imports. Module sources are retained for older browsers
and other fetch directives. A response that sets its own
`Content-Security-Policy` keeps it: the app policy is sent beside it as a
separate header, and browsers enforce their intersection, so a page can
tighten the policy (`frame-ancestors 'none'`, a `sandbox`) but never relax it.
The nonce goes into the app policy only; a response policy that restricts
`script-src` must allow the page's scripts itself, for example with
a `'nonce-…'` source built from `request.state.csp_nonce`. `X-Frame-Options`
stays `SAMEORIGIN`; CSP-aware browsers obey `frame-ancestors` instead, so a
page's `frame-ancestors 'none'` is only weaker in browsers without CSP level 2.

### `SessionMiddleware`

The framework's wrapper around Starlette's signed-cookie sessions. Cookie name is `session`; attributes are `HttpOnly`, `SameSite=Lax`. `SameSite=Lax` is the baseline CSRF defence: browsers don't attach the cookie to cross-site POST/PUT/DELETE, so a forged form submission from another origin is unauthenticated. Modules wanting defence in depth opt into the session-bound token check in `simple_module_hosting.auth.csrf` — `RequiresCsrf` as a router dependency, `get_csrf_token(request)` exposed as a view prop, and callers echoing it as `X-CSRF-Token` on unsafe methods.

### `TenantMiddleware` *(opt-in)*

Resolves the tenant — first from the authenticated user's `tenant_id`, then from a request header if one is configured — and sets both `request.state.tenant_id` and the `current_tenant_id` ContextVar. The `MultiTenantMixin` auto-filters SELECTs and auto-populates INSERTs using this value.

Header lookup is **off unless you name a header**: `tenant_header` defaults to `""`, which the host passes through as `header=None`. `X-Tenant-ID` is the conventional name (exported as `TENANT_HEADER`) but is not a default — set `SM_TENANT_HEADER=X-Tenant-ID` to actually enable that path. Both this and `SM_MULTI_TENANT` are read from env at boot; see [Host settings](/reference/env-vars#host-settings-hostsettings) for why a DB edit cannot change them.

### `LocaleMiddleware`

Resolves the active locale in this order per request:
1. Cookie named by `SM_I18N_COOKIE_NAME` (validated against supported locales).
2. `Accept-Language` header with q-value parsing and longest-prefix match (`es-MX` → `es`); a language sent with `q=0` is never chosen.
3. `SM_I18N_DEFAULT_LOCALE`.

The resolved locale lands on `request.state.locale` and is used by `InertiaLayoutDataMiddleware` to pick the translation bundle for the shared props.

### `InertiaLayoutDataMiddleware`

Permissions resolve eagerly for route guards. Other layout work is deferred in
`request.state.inertia_shared_factory`: menus, catalog selection, principal
serialization and module providers run only when a page needs them. Both
`get_inertia` and `render_error_page` await `resolve_inertia_shared(request)`;
its memoised task populates `request.state.inertia_shared` for existing readers.
JSON APIs and downloads do not invoke it. Custom readers should await the same
resolver before accessing the state dict.

When a page needs layout data, populates `request.state.inertia_shared` with:

- `auth.user`, `auth.isAuthenticated`, `auth.permissions`
- `menus` — grouped by `MenuSection`, filtered by the current user's permissions
- `i18n` — `{ locale, audience, supportedLocales, messages }` for the resolved locale

Inertia responses pick these up automatically via `InertiaDep` from `simple_module_hosting.frontend.inertia_deps`.

### Cache protection in `InertiaMiddleware`

Keeps the Inertia payload out of caches that answer page requests.

Every Inertia route serves one URL as two representations, chosen on the request's `X-Inertia` header: an HTML document for a full page load, a JSON payload for a client-side visit. Nothing in either response says so, which leaves a cache free to store one and hand back the other — visit a page through the SPA, then open the same URL directly, and the browser can serve the stored payload as the document. The visitor gets `{"component":"...","props":{...}}` where the page should be.

That only bites once a route marks itself cacheable, which a public-content module reasonably does. What makes it unsafe is the framework: `InertiaLayoutDataMiddleware` merges the signed-in user's `auth` block, permission list and menus into **every** payload. A route author choosing `Cache-Control: public` for their own page content has no way to know that — which makes this a disclosure bug, not just a broken page — so the guarantee lives here rather than in each module:

- **An Inertia payload is never stored.** `Cache-Control: private, no-store`, and the ETag is dropped so no cache can revalidate its way back to a copy it should not have kept. The cost is per-visit caching on client-side navigation, which was never safe to take: those bytes are specific to one user.
- **Both representations declare `Vary: X-Inertia`**, so a cache that honours `Vary` keeps them in separate entries. `Vary` is added to the document only when the response is HTML, so static assets and JSON APIs keep the validators and cache entries they had.

A module that wants its public page content cached should give the **document** its own `Cache-Control` and an ETag. That path is left alone — this middleware only governs the payload.

The exported adapter helper `is_inertia_request(scope)` uses header presence (`"X-Inertia" in headers`), not an equality check against `true`. The two must agree: if the library renders JSON for `X-Inertia: 1` while this middleware doesn't recognise it as Inertia, the payload goes back marked however the route marked it — reopening the leak by changing one header value.

### `MaintenanceMiddleware`

Serves everyone but admins a 503 page while `maintenance_mode` is set on `HostSettings`. See [Maintenance mode](/reference/deployment#maintenance-mode) for operating it.

The flag is DB-backed rather than an env var on purpose: flipping it must not require a redeploy, which is exactly the moment you least want one.

Admins pass through — someone has to be able to reach the settings screen and switch it back off. For the same reason the auth provider's own routes stay open, so an admin who was signed *out* when the switch flipped can still sign in. Three paths stay reachable regardless: `/health` and everything under `/health/` (so orchestrators don't kill the pod mid-maintenance), `/static/` and `/i18n/` (or the 503 renders unstyled and untranslated). Module routes registered through `register_public_routes` are honoured too, which is how branding's logo and favicon keep the maintenance page on-brand.

It **fails open** on missing config: a configuration gap taking the site down is the exact failure this feature would otherwise cause.

The middleware marks the request (`request.state.maintenance = True`) so the error page can tell a planned outage from the same status arriving unbidden. That matters most when the operator sets no message, which is the case where the page has nothing else to say.

### `CommitBeforeResponseMiddleware`

Finalizes the request's DB sessions at the ASGI `http.response.start` message — the last point still inside the request, late enough that response serialization has already run, early enough that a commit failure can still become a 500.

It exists because FastAPI runs a `yield` dependency's exit code *after* the response is delivered. `get_db` used to commit there, so a client that created a row and immediately read it back in a second request lost the race and got a deterministic 404 (GH #257).

Pure ASGI rather than `BaseHTTPMiddleware`, because the hook point is the `send` channel rather than the response object. `get_db` keeps the same commit in its own exit code as a fallback for when the middleware isn't in the stack; the session is claimed once, so whichever runs first wins.

> A request normally has exactly one session, since FastAPI caches the dependency. With several — `Depends(get_db, use_cache=False)` — a failure part-way through leaves the earlier commits durable while the client sees a 500. There is no cross-session atomicity to recover short of two-phase commit; the logged `db.session.commit_failed` is what makes it diagnosable.

## Inertia protocol responses

`InertiaMiddleware` comes from `simple_module_inertia` and runs just inside
`Session`, outside the default and after_tenant stages. It also normalises
redirects issued by middleware in those stages (an expired session's login
redirect after a `DELETE`).
For requests carrying `X-Inertia`, it converts 302 and 307 redirects after
PUT, PATCH, DELETE or QUERY into 303 responses. A redirect containing a
`#fragment` becomes an empty 409 with `X-Inertia-Redirect`, except for
`Purpose: prefetch` requests. An empty 200 becomes a 303 back to a safe
same-site Referer (or `/`).

Only the response start is held until the first body message when emptiness
needs checking. A positive Content-Length or a streaming first chunk passes
through immediately. Both Inertia and HTML responses receive `Vary: X-Inertia`;
existing Vary fields are retained and matched without case sensitivity.

## Module middleware stages

The hook stays `register_middleware(self, app)`. Existing
`app.add_middleware(...)` calls keep the default tier. To select a stage, use
`add_middleware` from `simple_module_hosting` with the same constructor arguments
as Starlette:

```python
from simple_module_hosting import add_middleware


def register_middleware(self, app):
    add_middleware(app, TenantAuditMiddleware, after="tenant")
    # Equivalent: stage="after_tenant"
```

| Stage | Request position | Available context / intended use |
| --- | --- | --- |
| `before_session` | Inside SecurityHeaders, immediately outside Session | Correlation ID and body protection; transport work that must precede session loading. No session, user, tenant or locale yet. |
| `default` (default) | Inside InertiaMiddleware, outside Tenant | Session; existing auth and module middleware. User availability depends on dependency order within this tier. |
| `after_tenant` / `after="tenant"` | Inside Tenant **and Locale**, before InertiaLayoutData | Session, resolved user, `request.state.tenant_id`, tenant ContextVar and `request.state.locale`. Layout permissions/shared props have not resolved yet. |

When Tenant is disabled, `after_tenant` still runs inside Locale; it does not
create a tenant context. A resolved tenant may be `None`, including anonymous
multi-tenant requests. Middleware must still honor tenant isolation.

Use either `stage` or `after="tenant"`; unknown values and conflicting selectors
raise `ValueError` at registration. The `before_session` stage sits outside the
Inertia adapter, so a middleware that short-circuits there owns its response's
protocol/cache semantics. Prefer `default` or `after_tenant` for page responses.
All stages remain inside BodyLimit and SecurityHeaders.

## Module middleware ordering

Hooks run in topological dependency order, with a stable module-name tiebreaker.
**Within each stage**, Starlette's LIFO rule applies: middleware registered later
wraps outermost and executes first on requests. Thus when `beta` depends on
`alpha` and both register in `after_tenant`, requests run
`Tenant → Locale → beta.mw → alpha.mw → InertiaLayoutData → … → app`.
The response reverses that order. Multiple additions from one hook also use LIFO.
Use `ModuleMeta.depends_on` for relative order; do not depend on names.

## Replacing or disabling a layer

Use the host's `customize(app)` callback, with helpers from
`simple_module_hosting`. For example, `ServerSideSession` is a host-owned
subclass of the framework's `SessionMiddleware` that implements server-side
storage and accepts the original constructor options:

```python
from simple_module_hosting import disable_middleware, replace_middleware
from simple_module_hosting.boot.host import build_host_app
from simple_module_hosting.pipeline.session import SessionMiddleware
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware


def customize(app):
    replace_middleware(
        app,
        SessionMiddleware,
        Middleware(ServerSideSession, store=session_store),
    )
    disable_middleware(app, GZipMiddleware)


app = build_host_app(__file__, customize=customize)
```

Targets are the exact installed class, not a string or a name match. This also
works for a module-owned layer such as Auth without a framework import of that
module. A replacement must be an explicit `starlette.middleware.Middleware`
object naming a **subclass of the target**. This is a deliberate contract opt-in:
subclassing does not prove its behavior, so the host must test its implementation
against the original guarantees. An unrelated ASGI callable or `None` is refused.

The replacement occupies the same position and merges constructor arguments by
parameter: explicitly supplied options override inherited values, whether passed
positionally or by keyword. Unspecified arguments retain their values. This preserves
session secret/key-provider and environment-dependent `https_only` defaults,
body/CORS registries, rate stores and security policy options. Replacements must
accept these constructor arguments. A Session subclass may implement storage
independently by overriding `__init__` and `__call__`.

Every replacement must preserve its target's request/response contract:

- **Session:** establish a mutable `scope["session"]` before HTTP/WebSocket
  consumers; load, persist and clear it across requests using an unforgeable
  cookie/session identifier. Honor expiry, remember-me and revocation state;
  do not resurrect cleared sessions. Keep HttpOnly, SameSite=Lax (or stricter)
  and the supplied `https_only` setting, since these underpin CSRF protection.
  Preserve session-bound CSRF values and login's clearing/rotation behavior.
  Tracking access/modification flags preserves cookieless public-file responses.
- **SecurityHeaders:** preserve CSP/nonce handling, dynamic registered sources,
  HSTS policy and the remaining security headers, including short circuits.
- **BodyLimit:** enforce the registered per-path byte ceilings, including streams.
- **RateLimit:** honor registered budgets, identity selection and error behavior.
- **Auth (module-owned):** resolve principals and enforce public-route exemptions
  and unauthenticated rejection before tenant/layout/route consumers.
- Other layers retain their documented ASGI, context and response behavior,
  especially tenancy, Inertia cache protection and commit-before-response.

`disable_middleware` has a closed allowlist:

| Allowed target | Why disabling is supported |
| --- | --- |
| `GZipMiddleware` | Compression only; a proxy can compress responses instead. |
| `RequestLoggingMiddleware` | Observability only; the host can supply access logs. Correlation IDs remain. |
| `ServerTimingMiddleware` | Development timing only; no request authorization or response protection. |

**Every other target refuses disabling**, including Session, SecurityHeaders,
BodyLimit, RateLimit and module Auth. Setup, Maintenance, Tenant and Inertia
cannot be disabled through this API either; their existing settings and module
selection semantics are unchanged. Replacing a layer requires the subclass
contract above even for the three optional layers.

Overrides must target exactly one installed layer. Missing targets raise
`KeyError`; duplicate installed targets or multiple overrides of the same target
raise `ValueError`. This includes requesting development-only ServerTiming in a
testing/production app. Stage insertion and overrides are finalized after
`customize`, before any request, so failures refuse app construction. The helpers
refuse later changes with `RuntimeError`; configure each app separately. Direct
mutation of `app.user_middleware` is not the supported override API.

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
