# site_lock

Optional site-wide password gate — a staging / pre-launch door. When enabled, every visitor must enter one shared password before they can see anything: not the landing page, not the API, not even that a login form exists.

**Off by default.** Installing the module changes nothing until an operator turns it on.

This is not user authentication — that is what [`auth`](/modules/auth), [`users`](/modules/users), and [`permissions`](/modules/permissions) are for. The site lock is one shared secret in front of everything, with no notion of identity.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `SiteLock` |
| `route_prefix` | *(none)* |
| `view_prefix` | *(none)* |
| `depends_on` | `["Settings", "Auth"]` |

Both dependencies are load-bearing. `Settings` lets `register_module_settings` reach the module registry. `Auth` makes this module sort *after* the auth module, and since middleware is installed in topological order while Starlette's `add_middleware` is LIFO, sorting later means wrapping **outermost** — so `SiteLockMiddleware` executes *before* `AuthMiddleware`.

That ordering is the point of the design: an anonymous visitor gets the gate rather than a redirect to the login page, so a locked site never reveals it has one. The order is pinned by `framework/hosting/tests/test_middleware_order.py`.

## Routes

The module registers **no routes**. The gate is served entirely from middleware at `/__unlock`, which keeps it reachable before auth runs and means a locked site serves exactly one document — no menus, no branding, no JS bundle. The gate keeps working even if the frontend build is broken.

| Method + path | Response |
|---|---|
| `GET /__unlock` | The gate page (200) |
| `POST /__unlock` | 303 to `next` on success; 401 on a wrong password; 429 when rate-limited |
| Other methods on `/__unlock` | 405 |

## Settings

DB-backed and hot-reloadable — changes apply immediately, no restart.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | `bool` | `false` | Master switch |
| `password` | `str` | `""` | The shared password. Masked in the admin UI |
| `message` | `str` | `""` | Optional line shown on the gate page |

Enabling with a blank password is rejected by a model validator, so the settings screen shows an error rather than gating the site behind the empty string.

## Behaviour when locked

| Request | Result |
|---|---|
| `/health*` | **Always passes.** Gating it would fail Kubernetes probes and get the pod killed |
| `/__unlock` | The gate page |
| `/api/*`, or any request with an `Authorization` header | `403 {"detail": "Site is locked"}` |
| Anything else | `302` to `/__unlock?next=…` |

A `403` rather than `401` is deliberate: a `401` would invite an auth flow that cannot succeed while the site is locked. Every gated response carries `Cache-Control: no-store`.

Unlock state lives in the signed session cookie. The stored marker is a fingerprint of the current password, so **rotating the password immediately invalidates every unlocked session**.

## Admin bypass and the lockout it does not cover

A user already holding a session with the `admin` role skips the gate. This is the intended escape hatch: enable the gate, mistype the password, and you are still holding the session that lets you go back to Settings and fix it. The bypass stamps the session marker on first use, so the provider lookup costs once per session rather than once per request.

**It only rescues a live session.** If no admin is signed in and the password has been forgotten, there is no in-app recovery — clear the override directly:

```sql
DELETE FROM settings_setting
 WHERE scope = 'system' AND key = 'site_lock.enabled';
```

Then restart the app (or save any setting) so the module re-hydrates.

## Brute-force protection

The unlock endpoint tracks failures per client IP in memory: 10 failures within 5 minutes trigger a 15-minute cooldown returning `429`. These thresholds are module constants, not settings — they are the only defence on a single shared secret, so they are not an operator-tunable surface.

The limiter is process-local, which suits the single-process staging deployments this module targets. It lives on the module state rather than inside the settings object, so an unrelated settings save cannot clear an in-flight cooldown.

## Open-redirect protection

The `next` target is sanitised before being echoed into the form or used in a redirect. Only same-site absolute paths are accepted; protocol-relative (`//host`), backslash-prefixed (`/\host`), and CR/LF-carrying values all fall back to `/`.
