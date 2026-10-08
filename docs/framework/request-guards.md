# Request guards: body size and rate limiting

Two pipeline-level guards protect the process before a route does any work.
Both are raw ASGI middleware in `simple_module_hosting`, configured from
`HostSettings` (env, then DB, then default) and extended by modules through a
registration hook.

| Guard | Answers | Default | Module hook |
|---|---|---|---|
| Body size (`BodyLimitMiddleware`) | `413` | 10 MiB | `register_body_limits` |
| Rate limit (`RateLimitMiddleware`) | `429` + `Retry-After` | `120/minute` per IP, anonymous public routes only | `rate=` on a public rule |

Both settings are read when the middleware stack is built, so editing them in
the admin UI needs a restart (the pre-app settings read picks the DB value up
on the next boot; an env var still wins).

## Body-size guard

A module's own payload check runs only after the framework has read the whole
body into memory, so it protects the database, not the process. The guard
refuses first:

- **`Content-Length` over the ceiling** is refused before anything reads the
  body.
- **No `Content-Length` (chunked)**, or one that lies, is caught by counting the
  bytes the app pulls through `receive` and aborting once the ceiling is
  crossed. A client cannot bypass the guard by streaming.

It sits right inside `RequestLogging` (so a 413 is logged with its correlation
id) and outside `GZip` and every module middleware.

### Response shape

Negotiated like every other error (`_wants_json`): API callers (`/api/*`, or an
explicit JSON `Accept`) get `413 {"detail": "...", "max_bytes": N}` immediately.
A browser request is not refused at the outer layer, because the error page needs
the session, locale and shared props the inner layers set up; instead the body
read raises `HTTPException(413)` and the app's normal handler renders the
Inertia error page. A route that never reads its body is therefore not
interrupted on that path.

### Settings

| Field | Env | Default |
|---|---|---|
| `max_request_body_bytes` | `SM_MAX_REQUEST_BODY_BYTES` | `10485760` (10 MiB); `0` disables the guard |

### Per-path overrides: `register_body_limits`

```python
def register_body_limits(self, registry: BodyLimitRegistry) -> None:
    # fixed ceiling
    registry.add_exact("/api/media/upload", 200 * 1024 * 1024, methods={"POST"})
    # a limit that is itself a runtime setting: pass a callable taking the app
    registry.add_prefix("/api/x/import", lambda app: app.state.x.settings.max_bytes)
```

Helpers: `add` (any match kind), `add_prefix`, `add_exact`, `add_regex`. The
first matching rule in registration order wins and *replaces* the global
ceiling, so it can lower it as well as raise it; `0` means unlimited for that
route. `file_storage` uses this for its upload endpoint: its ceiling is the
`max_file_size_bytes` setting plus 1 MiB of multipart framing.

## Rate limiter

Keyed on the client IP as the ASGI scope reports it, so `SM_TRUSTED_PROXY`
(`ProxyHeaders`, outermost) is honoured. It runs **after** the auth middleware
and after `Locale`/`InertiaLayoutData`, so it can tell anonymous from signed-in
and render a translated error page.

Policy:

1. A request is limited by `rate_limit_public` only if the auth middleware
   judged it anonymous-allowed **and** nobody is signed in. `AuthMiddleware`
   records that decision as `scope["state"]["auth_public"]` (framework defaults,
   the public-route registry and the provider's legacy public paths), and the
   limiter reads the flag, so the two cannot disagree, path variants included.
   The key is a plain scope-state contract (no import, SM009-safe). With no auth
   provider installed the registry match is used instead. `/health` and
   `/static/` are never limited.
2. A matching public rule's own `rate=` replaces that default and gets its own
   bucket per client.
3. `rate_limit_authenticated` (blank by default) opts signed-in traffic in.
4. Everything else, including routes outside the registry such as `/health` and
   `/static/`, is untouched.

### Settings

| Field | Env | Default |
|---|---|---|
| `rate_limit_public` | `SM_RATE_LIMIT_PUBLIC` | `120/minute`; blank or `off` disables |
| `rate_limit_authenticated` | `SM_RATE_LIMIT_AUTHENTICATED` | blank (off) |
| `redis_url` | `SM_REDIS_URL` | unset |

Rates read `<count>/<period>` with `second`, `minute`, `hour` or `day`
(`5/10s` for a multiple). A malformed rate fails at boot rather than silently
disabling protection.

Without `SM_TRUSTED_PROXY`, every client behind a reverse proxy appears as the
proxy's address and shares one anonymous bucket. Set it (or raise
`rate_limit_public`) before putting the host behind a proxy.

### Per-rule override

```python
def register_public_routes(self, registry) -> None:
    registry.add_regex(r"/api/gis/datasets/[^/]+/tilejson$", methods={"GET"}, rate="600/minute")
    registry.add_prefix("/api/records/public/", rate="60/minute")
    registry.add_prefix("/api/gis/stac", rate="off")  # exempt this rule
```

### Storage

- **Redis** when `SM_REDIS_URL` is set (needs the `redis` package, which
  `background_tasks` already installs): a fixed window, counted atomically with
  one Lua `INCR` + `PEXPIRE`, shared by every worker. Short socket timeouts keep
  a stalled Redis from hanging requests.
- **In process** otherwise: counters live in one worker, so with N workers the
  effective limit is up to N times the configured rate.
- **Degrades, never latches.** If Redis errors (down, timeout), hits are counted
  in per-worker counters instead (so the limit is weaker, not gone), a warning is
  logged (at most once a minute), and Redis is probed again after 5 seconds, so
  recovery is automatic. The script also re-arms a counter that lost its TTL, so
  no key can block an IP permanently. The limiter never takes requests down.

### Response shape

`429` with a `Retry-After` header (seconds until the window resets). API callers
get `{"detail": "...", "retry_after": N}`; browsers get the Inertia error page.

### Not covered

`users/auth_local/rate_limit.py` (`LoginRateLimiter`, `ThroughputLimiter`) stays
as it is: they are synchronous, per-key lockout and per-endpoint budget
primitives used from FastAPI dependencies, a different shape from this
middleware's async per-IP window.

## Where it lives

- `simple_module_core.body_limits.BodyLimitRegistry`, `simple_module_core.rate_limit`
  (rate parsing, in-process store), `PublicRoute.rate`
- `simple_module_hosting._body_limit`, `_rate_limit`, `_request_guard_responses`
- Wiring: `_phase_helpers.install_middleware`; registry on `app.state.body_limits`
