# Hosting feature batch 1: CORS, forwarded host, per-route rate limits, DB timeouts, OpenAPI security

Approved 2026-10-21 for #527, #528, #529, #531, #534. Defaults below were accepted.

## Shared (S0)

- Move the request-related `register_*` hooks out of `framework/core/simple_module_core/module.py`
  (299 lines) into a `_request_hooks.py` mixin; add no-op `register_cors_policies(registry)` and
  `register_rate_limits(registry)`.
- Core registries `CorsPolicyRegistry` and `RateLimitRegistry` (exact / prefix / regex matching,
  reusing the `PublicRoute` matcher as `BodyLimitRegistry` does), wired through
  `_registrations.py` / `app_builder.py` (≤300 lines) onto `app.state`.
- All new `HostSettings` fields with restart markers (`test_build_time_settings_marked.py`).
- Middleware slots in `install_middleware`; update the order docstring, `test_middleware_order.py`,
  CLAUDE.md § Middleware and `docs/framework/middleware.md`.

## #527 CORS

- Host settings (restart-required): `cors_allow_origins: list[str] = []` (empty → no API policy),
  `cors_allow_credentials: bool = True`, `cors_allow_methods = [GET, POST, PUT, PATCH, DELETE]`,
  `cors_allow_headers = [Authorization, Content-Type, X-CSRF-Token]`, `cors_expose_headers = []`,
  `cors_max_age: int = 600`; a validator rejects `*` with credentials. Host policy on prefix `/api/`.
- `CorsPolicy` frozen (origins, credentials, methods, headers, expose, max_age). Most specific match
  wins (exact, then regex/suffix, then longest prefix; ties keep the first and warn at boot).
- `hosting/_cors.py` dispatches to one pre-built Starlette `CORSMiddleware` per policy.
- Order: ProxyHeaders → ForwardedHost → CorrelationId → RequestLogging → **CORS** → BodyLimit → …
  (preflights never reach auth / rate limit / setup / maintenance).
- file_storage registers a policy for its public file path: origin `*`, no credentials,
  GET/HEAD/OPTIONS, allow `Range`/`If-Range`/`If-None-Match`, expose
  `Content-Range`/`Accept-Ranges`/`ETag`/`Content-Length`; `enabled=` reads a DB-backed module
  setting `public_files_cors: bool = True` (no restart). Document S3 presign redirects needing
  bucket CORS.

## #528 Forwarded host

- Host setting `forwarded_host_allowlist: list[str] = []` (exact host or `*.example.com`, optional
  port), restart-required; middleware installed only when `trusted_proxy` and the allowlist are set.
- Runs before ProxyHeaders sees the peer (added after it); own `ipaddress` trust check mirroring
  uvicorn's `*`/IP/CIDR rule. Leftmost `X-Forwarded-Host`; on match rewrite `host` header and
  `scope["server"]`; otherwise ignore with a debug log. `Forwarded:` (RFC 7239) unsupported.
- Docs: tenant subdomains need `*.<subdomain_base>` in the allowlist; email links keep using
  configured base URLs.

## #529 Per-route rate limits

- Core `RateLimitRule(rate, key: Literal["user","ip","user_or_ip","tenant"] = "user_or_ip",
  methods=None)`; hook `register_rate_limits(registry)`; rules apply to anonymous and signed-in
  requests before the existing public tiers.
- `RateLimit("10/minute", key="user")` FastAPI dependency using the shared store on `app.state.sm`;
  429 with `Retry-After`.
- Key resolution in `_rate_limit_keys.py`: user = principal id (token principal → owner); ip =
  `scope.client`; user_or_ip; tenant = `state.tenant_id`, falling back to user_or_ip.
  Buckets namespaced `rule:<kind>:<methods>:<pattern>:<keykind>=<id>`.
- Behaviour change: `rate_limit_authenticated` keyed by user, not IP (off by default).

## #531 DB timeouts

- Host settings (restart-required, env `SM_DB_*` still wins): `db_pool_timeout: int = 30`,
  `db_connect_timeout: int = 10`, `db_statement_timeout_ms: int = 0`,
  `db_idle_in_tx_timeout_ms: int = 0` (0 = off).
- `simple_module_db/engine_options.py`: asyncpg `{"timeout": c, "server_settings": {...}}`;
  psycopg2 `{"connect_timeout": c, "options": "-c statement_timeout=… -c
  idle_in_transaction_session_timeout=…"}`; SQLite nothing. Never applied to Alembic or the pre-app
  read.
- Worker: `SM_BG_TASKS_DB_POOL_SIZE` (2), `SM_BG_TASKS_DB_MAX_OVERFLOW` (3),
  `SM_BG_TASKS_DB_RECYCLE` (1800), optional `SM_BG_TASKS_DB_STATEMENT_TIMEOUT_MS`; the outbox async
  engine gets the same options. Document PgBouncer transaction mode rejecting startup params.

## #534 OpenAPI security

- `components.securitySchemes`: `bearerAuth` (http bearer) and `sessionCookie` (apiKey, cookie
  `session`). Operations: `security: []` when public (PublicRouteRegistry match on the templated
  path, legacy provider public paths, the openapi URL); otherwise
  `[{bearerAuth: []}, {sessionCookie: []}]`.
- Doctor SM031 (WARNING): an `/api` route with no permission/allow gate and no public match;
  `Authenticated()` marker (new gate kind, still refuses tokens where appropriate) silences it.
  Runs where a built app is available (dev boot; check `make doctor`).

## Tests (acceptance)

Preflight from an allowlisted origin succeeds with credentials and never 401s; non-allowlisted
origin gets no CORS headers; cross-origin Range GET on a public file → 206 with exposed
`Content-Range`; forged forwarded host ignored, allowlisted one used by `url_for`; two users on one
IP get separate 10/minute budgets, anonymous falls back to IP; timeouts produce the right connect
args per driver (Postgres `pg_sleep` test marked `postgres`); exported schema lists security per
operation; SM031 fires and is silenced by the marker.
