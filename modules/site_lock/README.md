# simple_module_site_lock

Optional site-wide password gate for `simple_module` apps — a staging /
pre-launch door. When enabled, every visitor must enter one shared password
before they can see anything: not the landing page, not the API, not even
that a login form exists.

**Off by default.** Installing this module changes nothing until an operator
turns it on.

## How it works

The module installs a single middleware that runs *before* `AuthMiddleware`.
That ordering is the whole point — an anonymous visitor gets the gate rather
than a redirect to the login page, so a locked site never reveals that it has
one.

It achieves that ordering by declaring `depends_on=["Settings", "Auth"]`:
modules are installed in topological order and Starlette's `add_middleware`
is LIFO, so sorting after `Auth` makes this middleware wrap outermost.

Unlock state lives in the signed session cookie. The stored marker is a
fingerprint of the current password, so **rotating the password immediately
invalidates every unlocked session**.

## Enabling it

Settings → Site Lock:

| Field | Default | Meaning |
|---|---|---|
| `enabled` | `false` | Master switch |
| `password` | `""` | The shared password. Masked in the admin UI |
| `message` | `""` | Optional line shown on the gate page |

Changes apply immediately — no restart. Enabling with a blank password is
rejected by a validator, so you cannot accidentally gate the site behind the
empty string.

## What stays reachable when locked

- `/health` — always. Gating it would fail Kubernetes liveness/readiness
  probes and get the pod killed.
- `/__unlock` — the gate page itself.

Everything else is gated. Requests under `/api/`, and any request carrying an
`Authorization` header, get `403 {"detail": "Site is locked"}` rather than a
redirect — a `401` would invite an auth flow that cannot succeed while the
site is locked. Browser requests get a `302` to the gate.

## Admin bypass, and the lockout you can still cause

A user who already holds a session with the `admin` role skips the gate.
This is the intended escape hatch: if you enable the gate and mistype the
password, you are still holding the session that lets you go straight back to
Settings and fix it.

**It only rescues a live session.** If no admin is currently signed in and the
password has been forgotten, there is no in-app recovery. Clear the override
directly in the database:

```sql
DELETE FROM settings_setting
 WHERE scope = 'system' AND key = 'site_lock.enabled';
```

Then restart the app (or save any setting) so the module re-hydrates.

## Brute-force protection

The unlock endpoint tracks failures per client IP in memory: 10 failures
within 5 minutes trigger a 15-minute cooldown returning `429`. These
thresholds are module constants, not settings — they are the only defence on
a single shared secret, so they are not an operator-tunable surface.

The limiter is process-local, which is adequate for the single-process
staging deployments this module targets.

## What this is not

This is not user authentication or authorisation — that is what the `auth`,
`users`, and `permissions` modules are for. The site lock is one shared
secret in front of everything, with no notion of identity.
