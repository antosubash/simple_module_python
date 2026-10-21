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
| `depends_on` | `Auth`, `Users` (optional: `Settings`) |

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

### Which routes a token may reach

The cap works on **permissions**, so on its own it could not constrain a route
that asks only for a signed-in principal. The framework closes that gap with a
fail-closed rule, enforced by `simple_module_hosting.token_guard` as an
app-wide dependency on every `APIRoute` (module, host and framework routes):

| Route | A token (`scopes` set) gets |
|---|---|
| Has a permission gate in its dependency tree — `RequiresPermission(...)` or `auth.deps.require_permission(...)` | admitted; the gate decides, capped at the scopes |
| A page — on a module view router, or depends on `InertiaDep` | **403**, even when gated: page props are a second, unscoped read API |
| Marked `Depends(TokenAllowed())` | admitted, with no permission check — use only for routes harmless for any token |
| Anything else | **403** (JSON on `/api/*`) |
| A public route (exempted from auth) without a gate | served, but **as anonymous**: the token's principal is dropped, and so is the tenant it pinned |

So a token cannot create or leave an organisation (`/api/tenants/`), switch
tenant, open `/users/me`, the dashboard or any other page, whatever its scopes.
The decision is computed once per route from its dependency tree — include-level
`include_router(..., dependencies=[...])` gates included — and cached.
Browser sessions and a provider's own bearer tokens (`auth_kind == "bearer"`)
are unscoped and never affected. A route that checks a permission inline in its
handler rather than through a dependency is refused for tokens; move the check
into `RequiresPermission` if tokens should reach it.

The `users` self-service routes (`/api/users/me`, password change, sign out
everywhere) authenticate through the session cookie only and never see a token.

## Creating tokens

| Rule | Where |
|---|---|
| Scopes must be non-empty registered permissions the creator holds **now** (`*` is never assignable) | create endpoints |
| Expiry is required and at most `max_lifetime_days` (setting, default 365) | service |
| Service key roles: platform roles only — never `admin`, never `tenant:*` | admin endpoint + service + resolver |
| Only a **cookie session** may create, list or revoke tokens: `auth_kind == "session"` and no `Authorization` header. A token, a `users` access token or a Keycloak JWT gets 403 | every endpoint and page |
| The creator must be an active account in the app's [user directory](/framework/user-directory) whose roles are known; otherwise 400 `api_tokens.errors.account_required`. Under Keycloak roles live in the IdP, so personal tokens are refused there | personal create endpoint |
| Cookie-authenticated mutations require `X-CSRF-Token` (`RequiresCsrf`) | every mutation |

## Tenancy

The table uses `MultiTenantMixin`; rows are stamped with the active tenant.

- **Personal tokens** are pinned to the tenant they were created in, exactly
  like service keys: the `tenants` resolver binds that tenant and ignores the
  tenant header, subdomains and the session preference. The owner must still be
  an **active member** of it: once they are removed, or the tenant is suspended,
  the token is de-authenticated (401) — it does not fall back to another of the
  owner's organisations. A user's own list spans every tenant, so a token made
  in one organisation can be revoked from another; the tenant's admins see it
  in `/admin/api-tokens/` of that tenant.
- **Service keys** are pinned to the tenant they were created in. The
  `tenants` resolver binds that tenant (while it exists and is active) and
  ignores headers and subdomains. A token's tenant answer varies on
  `Authorization` only.
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
| `POST` | `/api/api_tokens/tokens/revoke-all` | Revoke every own personal token ("Revoke all" on the page) |
| `GET` | `/api/api_tokens/admin/tokens` | Every token in the active tenant |
| `POST` | `/api/api_tokens/admin/service-keys` | Create a service key |
| `POST` | `/api/api_tokens/admin/tokens/{id}/revoke` | Revoke any token in the tenant |

## Security model

Decisions made after the security review of #455, and why:

- **Tokens survive a password change and "sign out everywhere".** That matches
  GitHub and most platforms: a token is a deliberate, separately managed
  credential, and a password rotation should not silently break every CI job.
  End them explicitly — individually, or with **Revoke all** on `/api-tokens/`
  (`POST /api/api_tokens/tokens/revoke-all`), which is the step to take after
  a suspected compromise.
- **Re-enabling a disabled user revives their unexpired tokens.** Disabling is
  a reversible suspension; the resolver refuses every token while the account
  is disabled. If the account was disabled because of a compromise, revoke its
  tokens (the admin list) before re-enabling it.
- **No token-specific rate limit.** Token requests are signed-in requests and
  go through the existing middleware only. A token is 256 bits, so guessing is
  not a practical attack; each well-formed bearer costs one indexed lookup.
- **Token management needs a person at a keyboard** — a cookie session with no
  `Authorization` header. A `users` access token (`/api/users/auth/token`) or a
  Keycloak JWT is a `"bearer"` principal: it keeps its user's full rights
  (no scope cap) but cannot mint, list or revoke tokens, so a short-lived
  credential cannot be turned into a year-long one.
- **Tokens never reach pages or ungated routes** (see *Which routes a token may
  reach*). A service key's `svc:` principal therefore never reaches code that
  expects an account id.
- **Stored roles are re-filtered**: the resolver drops `admin` and `tenant:*`
  from a service key's row, so a hand-edited row cannot make a key an admin or
  a tenant owner.
- **A personal token needs its owner to still hold `api_tokens.use`.** The
  principal carries `required_permission = "api_tokens.use"`, checked on every
  request against the owner's live permissions — roles, the tenant role in the
  token's tenant, and grant sources — before the scope cap. Without it the
  request runs as anonymous, so a gated route answers **401**, as for a revoked
  token. Taking `api_tokens.use` away also takes away listing and revoking
  tokens, so it retires them all at once rather than leaving them unmanageable.
  Service keys require nothing: they are governed by `api_tokens.manage`
  holders, not by an owner.
- **A token's pages show no one.** Tokens are refused on pages, but a 403 page,
  or a public page served to a demoted token, still renders a layout: its
  shared props (`auth`, `menus`, the `tenant` memberships) describe the
  anonymous visitor, never the token's owner.

## Audit

Create and revoke are recorded by `AuditMixin`. `token_hash` and
`last_used_at` are excluded from the recorded changes. Audit rows link back to
`/admin/api-tokens/?token=<id>` and are labelled `name (prefix…)`.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `max_lifetime_days` | `365` | Longest expiry a new token may get (1–3650). Existing tokens keep theirs. |

DB-backed (edited in the settings admin), like other module settings.
