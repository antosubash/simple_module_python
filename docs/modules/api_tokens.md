# api_tokens

Personal access tokens (PATs) and service API keys. A script, CI job or another
service sends `Authorization: Bearer <token>` and is treated as a principal
whose permissions are **capped by the token's scopes**. Tokens are hashed at
rest, shown once, and revocable with effect on the next request.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `ApiTokens` |
| `route_prefix` | `/api/api_tokens` |
| `view_prefix` | `/api-tokens` |
| `admin_view_prefix` | `/admin/api-tokens` |
| `depends_on` | `Auth`, `Users`, `Settings` |

Installed in this repository's host. It is **not** part of the `smpy new`
scaffold; add `simple_module_api_tokens` to a host's dependencies to enable it,
then generate a migration (its first revision carries
`branch_labels = ("api_tokens",)`).

## Token kinds

| Kind | Format | Acts as | Permissions |
|---|---|---|---|
| Personal access token | `smpat_<43 base62 chars>` | its owner (a `users` account) | owner's **live** roles and grants ∩ scopes |
| Service key | `smsk_<43 base62 chars>` | `svc:<token id>` — no person | roles chosen at creation ∩ scopes |

The secret is 32 bytes from `secrets.token_bytes`, base62-encoded and padded to
a fixed width. Only `sha256(token)` is stored, with an 8-character display
prefix (`smpat_AbCd1234…`) so people can tell tokens apart. The plaintext is in
the create response and nowhere else.

## How a request is resolved

1. The auth provider (`users`, and `keycloak`) sees a bearer value starting
   with `smpat_` / `smsk_` and returns `None` immediately — no wasted lookup
   in its own token store.
2. `AuthMiddleware` falls through to the principal-resolver chain, where this
   module's resolver is registered at startup.
3. The resolver checks the format with a regex, then does **one indexed lookup
   by hash** (no cache). Revoked, expired or unknown → `None` → 401.
4. A PAT also loads its owner with roles; an inactive or disabled owner → 401.
5. The principal is a `UserContext` with `auth_kind` (`"pat"` / `"service"`)
   and `scopes` set. `last_used_at` is written at most once every 5 minutes,
   by a conditional `UPDATE` in its own short transaction.

Because nothing is cached, a token keeps working across restarts and stops on
the very next request after it is revoked.

## The scope cap

`UserContext.scopes` is `None` for an ordinary session. For a token it is a
list, and:

- `resolve_principal_permissions` (used by `RequiresPermission`, the menu
  filter and the frontend's `auth.permissions`) intersects the resolved set
  with the scopes. An admin's wildcard expands to the scope list only.
- `auth.deps.require_permission` skips its admin-role shortcut.
- Role-only admin gates (`/admin`, the Doctor page, the maintenance bypass) use
  `simple_module_core.permissions.is_admin_principal`, which is `False` for any
  token.

So an admin's token with scope `feature_flags.view` can `GET /api/feature_flags/`
and nothing else. The cap sits on top of the owner's live grants, so demoting
the owner shrinks every token they hold at once.

If you write a check that admits admins by role, use `is_admin_principal(user)`
rather than `is_admin(user.roles)`.

The cap works on **permissions**. A route that asks only for an authenticated
principal (`CurrentUser`, `request.state.user`) and checks no permission is
reachable by any valid token of that user, whatever its scopes. Gate anything
a token should not do with a permission, or refuse
`user.auth_kind != "session"` the way this module's own endpoints do. The
`users` self-service routes (`/api/users/me`, password change, sign out
everywhere) authenticate through the session cookie only and never see a token.

## Creating tokens

| Rule | Where |
|---|---|
| Scopes must be non-empty registered permissions the creator holds **now** (`*` is never assignable) | create endpoints |
| Expiry is required and at most `max_lifetime_days` (setting, default 365) | service |
| Service key roles: platform roles only — never `admin`, never `tenant:*` | admin endpoint + service + resolver |
| Only a **session** may create, list or revoke tokens (`auth_kind == "session"`); a token gets 403 | every endpoint and page |
| Cookie-authenticated mutations require `X-CSRF-Token` (`RequiresCsrf`) | every mutation |

## Tenancy

The table uses `MultiTenantMixin`; rows are stamped with the active tenant.

- **Personal tokens** follow their owner like a session would: the tenant
  resolver picks from the owner's memberships (or the tenant header). A user's
  own list spans every tenant, so a token made in one organisation can be
  revoked from another.
- **Service keys** are pinned to the tenant they were created in. The
  `tenants` resolver binds that tenant (while it exists and is active) and
  ignores headers and subdomains.
- The admin list and admin revoke act on the **active** tenant only. With
  strict tenancy and no active tenant the page says so; the API answers 409.

## Permissions

| Permission | Default holders | Grants |
|---|---|---|
| `api_tokens.use` | `user`, `tenant:member`/`admin`/`owner` | own personal tokens at `/api-tokens/` |
| `api_tokens.manage` | `admin` | every token in the tenant, service keys, at `/admin/api-tokens/` |

## Routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api-tokens/` | Page `ApiTokens/Index` (user dropdown, "API tokens") |
| `GET` | `/admin/api-tokens/` | Page `ApiTokens/Admin` (admin sidebar, Access group) |
| `GET` / `POST` | `/api/api_tokens/tokens/` | List / create own personal tokens |
| `POST` | `/api/api_tokens/tokens/{id}/revoke` | Revoke own token |
| `GET` | `/api/api_tokens/admin/tokens` | Every token in the active tenant |
| `POST` | `/api/api_tokens/admin/service-keys` | Create a service key |
| `POST` | `/api/api_tokens/admin/tokens/{id}/revoke` | Revoke any token in the tenant |

## Audit

Create and revoke are recorded by `AuditMixin`. `token_hash` and
`last_used_at` are excluded from the recorded changes. Audit rows link back to
`/admin/api-tokens/?token=<id>` and are labelled `name (prefix…)`.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `max_lifetime_days` | `365` | Longest expiry a new token may get (1–3650). Existing tokens keep theirs. |

DB-backed (edited in the settings admin), like other module settings.
