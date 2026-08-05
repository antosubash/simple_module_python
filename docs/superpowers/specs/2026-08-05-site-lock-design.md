# Site Lock: optional site-wide password gate

**Date:** 2026-08-05
**Status:** approved-to-implement (proceeding under an active `/goal` directive)

## Goal

Let an operator hide the entire site behind a single shared password — a
staging / pre-launch gate. Anyone without the password sees nothing: not the
landing page, not the API, not even that a login form exists.

**Off by default.** A deployment that never touches the setting behaves exactly
as it does today, and the disabled path must cost effectively nothing per
request.

## Current state

- Modules install middleware via `ModuleBase.register_middleware(app)`. The
  host calls these in topological order inside `install_middleware`
  (`framework/hosting/simple_module_hosting/_phase_helpers.py`). Because
  Starlette's `add_middleware` is LIFO, **a module that sorts later wraps
  outermost**.
- `AuthMiddleware` (`modules/auth/auth/middleware.py`) resolves the user via
  the single registered `AuthProvider`, then redirects unauthenticated browser
  requests to the provider's login URL and returns 401 JSON for `/api/*`.
- Public paths come from two places only: the `_FRAMEWORK_PUBLIC_*` constants
  in the auth middleware, and `provider.get_public_paths()`. **There is no
  registry a third module can add to** — this is what rules out mounting a
  normal view route for the gate page without first extending the auth module.
- DB-backed per-module settings go through
  `settings.registration.register_module_settings(app, package, cls, factory)`,
  hydrate at startup, and hot-swap through
  `settings.reload.apply_changes_and_reload` which publishes `SettingsReloaded`.
- `settings/_module_settings.py` masks any field whose name matches
  `(password|secret|api[_-]?key|private[_-]?key|token[_-]?secret)` in the admin
  UI.
- `UserContext` (`modules/auth/auth/contracts/schemas.py`) exposes
  `roles: list[str]`; the admin role name is `"admin"`
  (`users.constants.ADMIN_ROLE_NAME`).

## Decisions

Settled during brainstorming:

1. **Staging / pre-launch gate** — one shared password in front of the whole
   site, including the login page. Not a "public pages only" gate, not a
   maintenance-mode banner.
2. **Configured from the admin UI only** (DB-backed). No `SM_SITE_LOCK_*` env
   vars.
3. **Logged-in admins always bypass** the gate — this is the lockout escape
   hatch, chosen over shipping a CLI command.
4. **Self-contained middleware-rendered gate page**, not an Inertia `.tsx` page.
   This avoids extending the auth module with a public-paths registry, and
   means a locked site serves exactly one page and leaks nothing else.

## Design

A new module `modules/site_lock/` that installs exactly one middleware. No
models, no migration, no `.tsx` pages, no routes registered with the app router.

### 1. Placement in the pipeline

```python
meta = ModuleMeta(name="SiteLock", depends_on=["Settings", "Auth"])
```

- `Settings` — so `register_module_settings` can reach
  `app.state.settings.module_registry` during `register_settings`.
- `Auth` — puts SiteLock after Auth in topological order, so its
  `add_middleware` call happens later, so it **wraps outermost and executes
  before `AuthMiddleware`**.

Resulting order on a request:

```
CorrelationId → RequestLogging → SecurityHeaders → Session → [SiteLock] → Auth → Locale → InertiaLayoutData → app
```

Running before Auth is what makes an anonymous visitor see the gate rather than
a redirect to `/users/login`. `SessionMiddleware` sits *outside* SiteLock, so
`scope["session"]` is readable and writes are persisted on the way out — the
same mechanism `AuthMiddleware` already relies on for its `next` key.

Raw ASGI class, not `BaseHTTPMiddleware`, per the convention stated in
`framework/hosting/simple_module_hosting/middleware.py`.

### 2. Settings

`SiteLockSettings(BaseSettings)`, registered as package `site_lock`, DB-backed
and hot-reloadable:

| Field | Type | Default | Notes |
|---|---|---|---|
| `enabled` | `bool` | `False` | the off-by-default guarantee |
| `password` | `str` | `""` | name contains `password` → auto-masked in the settings UI |
| `message` | `str` | `""` | optional line shown on the gate page |

A `@model_validator` rejects `enabled=True` with a blank/whitespace password, so
`apply_changes_and_reload` raises a `ValidationError` and the settings screen
refuses the change rather than gating the site behind an empty string.

State object `SiteLockState(settings=...)` on `app.state.site_lock`, satisfying
`SM012`.

### 3. Request handling

In order:

1. `scope["type"] != "http"` → pass through (websockets are not gated).
2. `not settings.enabled` → pass through. **The default-off fast path: one
   attribute read and a boolean test — no `Request` construction, no
   allocation.**
3. Path is `/health` (prefix) → pass through, always. Gating it would fail
   Kubernetes liveness/readiness probes and get the pod killed.
4. Path is the unlock endpoint `/__unlock`:
   - `GET` → serve the gate page (200).
   - `POST` → read the form body, compare with `secrets.compare_digest`. On
     success, write the session marker and `303` to the sanitised `next`
     target. On failure, re-serve the page with an error and status `401`.
   - Any other method → `405`.
5. `scope["session"].get("site_lock") == fingerprint` → pass through. The
   fingerprint is a truncated `sha256` of the current password, so **rotating
   the password invalidates every existing unlock session**.
6. Admin bypass: resolve via `app.state.auth.auth_provider.resolve_user(request)`.
   If a user comes back and `"admin"` is in `user.roles`, stamp the session
   marker and pass through. Stamping is what keeps this to **one resolve per
   session rather than one per request**. Guarded for a `None` provider and for
   a provider that raises.
7. Otherwise the request is gated:
   - `/api/*` prefix, or an `Authorization` header present → `403` JSON
     `{"detail": "Site is locked"}`. 403 rather than 401 so clients do not
     start an auth flow that cannot succeed.
   - Everything else → `302` to `/__unlock?next=<current path>`.

All gate and gated responses carry `Cache-Control: no-store` so no proxy or CDN
caches either the gate page or a gated response.

### 4. The gate page

`site_lock/templates/unlock.html` — one self-contained file with inlined CSS,
read once at import time and cached in a module-level constant. Rendered by
plain string substitution (`string.Template`), not Jinja, to avoid wiring a
template loader for a single static asset.

Every interpolated value (`message`, `next`, error text) is passed through
`html.escape`. Because the page needs no external CSS or JS, `/static/` needs
no exemption — a locked site serves exactly one page and nothing else.

`next` is sanitised before being echoed into the form or used in a redirect:
only same-site absolute paths (starting with a single `/`, not `//`) are
accepted, anything else falls back to `/`. This prevents the gate from being
used as an open redirect.

### 5. Brute-force protection

One shared secret is the whole security boundary here, so the unlock endpoint
needs a limiter. `users` already has `LoginRateLimiter`, but importing it would
hard-couple `site_lock` to `users` and break under the `keycloak` provider.

A small in-memory per-IP limiter lives in `site_lock/rate_limit.py`: **10 failed
attempts within 5 minutes** trigger a **15-minute cooldown** during which
`POST /__unlock` returns `429`. In-memory is consistent with the existing
`users` limiter and adequate for the single-process staging deployments this
feature targets.

These three thresholds are **module-level constants, not settings fields** —
they are not part of the configurable surface. Keeping them out of
`SiteLockSettings` keeps the admin UI to the three fields that matter and
avoids offering an operator a way to weaken the only brute-force defence.

Client IP comes from `scope["client"]`, which is what the app already trusts.

## Known limitation: cold-start lockout

The admin bypass rescues an admin who **already holds a live session**. That
covers the realistic footgun: you enable the gate, typo the password, and are
still holding the session that lets you go straight back to Settings and fix it.

It does **not** cover a cold start — session expired, password forgotten, no
admin currently signed in. Recovery then requires deleting the settings
override row directly in the database. This was an explicit choice (admin
bypass was selected over shipping a `smpy site-lock disable` CLI command) and
is documented in the module README. Adding the CLI command later is a
self-contained follow-up.

## Testing

- Disabled by default: a request passes through untouched, and the middleware
  does not touch the session or the auth provider.
- Enabled, no session: browser request → `302 /__unlock`; `/api/*` → `403` JSON.
- `/health` is never gated, enabled or not.
- Correct password → session marker set → the next request passes through.
- Wrong password → `401`, no session marker written.
- Rotating the password invalidates a previously-valid unlock session.
- An admin with a live session bypasses; an authenticated **non-admin** does not.
- The validator rejects `enabled=True` with a blank password.
- `next` sanitisation rejects `//evil.example` and absolute URLs.
- Rate limiter returns `429` after the configured number of failures.
- Middleware ordering: SiteLock wraps outside `AuthMiddleware` — follow the
  existing `framework/hosting/tests/test_middleware_order.py` pattern.

## Out of scope

- Per-user or per-role gating (that is what the existing auth system is for).
- Persisting unlock state anywhere other than the signed session cookie.
- A distributed/Redis-backed rate limiter.
- Env-var configuration (explicitly declined — admin UI only).
- A `smpy site-lock disable` CLI command (see the lockout limitation above).

## Non-effects

No migration (no models). No `make gen-pages` run (no `.tsx`). Trips no
`make doctor` diagnostics: `SM012` is satisfied by `app.state.site_lock`,
`SM017` and `SM019` do not apply because the module ships no pages and
registers no view routes.
