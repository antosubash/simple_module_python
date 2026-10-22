# CORS

Cross-origin access is opt-in per path. A request no policy matches passes
through untouched and gets no CORS headers.

## Host API policy

Set `cors_allow_origins` (Settings admin screen, group CORS, or
`SM_CORS_ALLOW_ORIGINS`) and the host registers one policy on the `/api/` prefix.
Empty (the default) registers nothing.

| Setting | Default |
|---|---|
| `cors_allow_origins` | `[]` (no policy) |
| `cors_allow_credentials` | `true` |
| `cors_allow_methods` | `GET, POST, PUT, PATCH, DELETE` |
| `cors_allow_headers` | `Authorization, Content-Type, X-CSRF-Token` |
| `cors_expose_headers` | `[]` |
| `cors_max_age` | `600` |

`*` is refused while `cors_allow_credentials` is on. All of these are
restart-required: the middleware is built at boot.

## Module policies

A module with a public, cross-origin surface declares it in
`register_cors_policies(registry)`:

```python
def register_cors_policies(self, registry):
    registry.add_regex(
        PUBLIC_PATH_PATTERN,
        CorsPolicy(origins=("*",), allow_credentials=False, methods=("GET", "HEAD")),
        enabled=lambda: self._toggle_is_on(),
    )
```

`add_exact`, `add_prefix` and `add_regex` match on the request path. The most
specific match wins (exact, then regex, then longest prefix); a tie keeps the
first registration and logs a warning. `enabled=` is evaluated per request, so a
DB-backed toggle needs no restart.

## Where it runs

`CorsMiddleware` sits between `RequestLogging` and `BodyLimit`. A preflight is
answered before auth, rate limiting, the setup gate or maintenance mode can
reject it, and a `413` from `BodyLimit` still carries the CORS headers the
browser needs to read it. One Starlette `CORSMiddleware` is built per policy.
