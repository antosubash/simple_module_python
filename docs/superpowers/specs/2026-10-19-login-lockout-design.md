# Login lockout across workers and source IPs (GH #530)

Approved 2026-10-19.

## Problem

`modules/users/users/auth_local/rate_limit.py` keeps failure counters and locks in
process-local `TTLCache`s. The key is `username::ip`, and only
`POST /api/users/auth/login` consults them. The consequences:

- With N workers, the effective threshold is N× the configured one.
- An attacker who rotates source IPs never trips the lock for an account.
- A restart clears every lock.
- `POST /api/users/auth/token` has no lockout and no throttle.
- The stock fastapi-users route `/api/users/auth-inner/login` has no throttle.

## Design

### Tier 1 — account lock (database)

New nullable columns on `users_user`, added by one Alembic migration in
`host/migrations/versions/` that chains off the current users head:

| column | type | default |
|---|---|---|
| `failed_login_count` | int, not null | `0` (server default) |
| `last_failed_login_at` | `AwareDateTime`, nullable | — |
| `locked_until` | `AwareDateTime`, nullable | — |

On a failed password login for an existing user, a single
`UPDATE users_user … RETURNING failed_login_count` does the bookkeeping:

- It increments the count.
- It resets the count to 1 when `last_failed_login_at` is older than
  `login_rate_limit_window_seconds`.
- It stamps `last_failed_login_at`.

The update is atomic across workers. When the returned count reaches
`login_lockout_account_failures`, the user row is loaded through the ORM and
updated:

- `locked_until` = now + `login_rate_limit_cooldown_seconds`;
- `failed_login_count` = 0.

Going through the ORM means the automatic audit capture records the lock.

A successful login resets `failed_login_count` to 0 and clears
`last_failed_login_at`.

While `locked_until > now`, every password login for that account gets a 429,
the correct password included. The response carries `Retry-After` and the
existing detail, "Too many attempts — try again later".

### Tier 2 — per-IP + account throttle (host rate-limit store)

The existing "5 failures from one IP within the window" check moves onto the
host's rate-limit `WindowStore`. That store is Redis-backed when `SM_REDIS_URL`
is set and in-process otherwise. The framework exposes the store it already
builds on `app.state.sm` (`rate_limit_store`); no new Redis client is created.

The keys are:

- `login:ip:<ip>:<username>` for failures from one IP.
- `login:acct:<username>` for a username with **no** account. Unknown usernames
  are counted against the account threshold here, so a 429 does not reveal
  whether an account exists.

A key that is over its limit refuses further attempts until its window ends.

### Login paths

Both login routes use one helper, `auth_local/lockout.py`:

- **`/api/users/auth/login`** (session login).
- **`/api/users/auth/token`** — gains both tiers. It returns 429 when locked, and
  its existing 401 for bad credentials is unchanged.

The steps, in order:

1. Refuse if locked: tier 1 by `locked_until`, tier 2 by store keys.
2. Authenticate.
3. On failure, record it in both tiers.
4. On success, reset tier 1.

Two other changes to the login surface:

- The stock `/api/users/auth-inner/login` is no longer mounted. Its logout
  stays, unless nothing uses it either. The wrappers already shadow it, and its
  callers are grepped first.
- The in-process `LoginRateLimiter` is removed once nothing uses it.
  `ThroughputLimiter` (register, forgot-password and the other routes) is
  unchanged.

### Settings (`UsersSettings`)

- New: `login_lockout_account_failures: int = Field(10, ge=1)`.
- Existing settings keep their meaning:
  - `login_rate_limit_failures` (5) — tier-2 threshold.
  - `login_rate_limit_window_seconds` (300) — window for both tiers.
  - `login_rate_limit_cooldown_seconds` (900) — account lock length.

The account default is 10 rather than the issue's 5. With 5, anyone who knows
an email could lock its owner out from any network. Tier 2 still stops a single
source after 5.

### Admin

- `PATCH /api/users/admin/{id}/unlock` clears `locked_until`,
  `failed_login_count` and `last_failed_login_at` through the ORM, so the
  unlock is audited.
- `UserListItem` gains `locked_until`.
- The user edit page shows "Locked until <time>" and an Unlock action.
- The users list shows a "locked" badge.
- All copy goes through i18n keys.

### Audit

Lock and unlock are ORM writes on `User`, so `snapshot_changes` records them.
`failed_login_count` and `last_failed_login_at` are added to the excluded
audit fields, so failed attempts don't flood the audit log.

## Tests

- **Acceptance:** with `login_lockout_account_failures=5`, five failures for
  `alice` lock her. The failures come from 3 client IPs (via
  `ASGITransport(client=…)`) and 2 app instances sharing one database file.
  The lock survives building a fresh app on the same database.
- `/auth/token` is refused with 429 while the account is locked.
- A successful login resets the count, and an expired window restarts it.
- Unknown usernames and locked accounts return the same 429.
- Tier 2: 5 failures from one IP throttle that IP for that account, and a
  different IP is still allowed until tier 1 trips.
- Admin unlock clears the lock, and the lock and unlock audit rows exist. The
  counter changes write no audit rows.
- A vitest covers the edit page's locked state and the Unlock action.
- Migration: `alembic check` is clean, and `make migrations-roundtrip-pg` passes
  if Postgres is available.

## Out of scope

OAuth, Keycloak and invite-link sign-ins: they involve no password.
