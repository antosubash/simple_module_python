# simple_module_oidc

Generic **OpenID Connect** authentication provider for simple_module — with
**native Microsoft Entra ID (Azure AD)** support, plus Auth0, Okta, Zitadel,
Authentik, Keycloak, and any OIDC-compliant identity provider.

The module is configured from a provider's OIDC **discovery document**
(`.well-known/openid-configuration`), so endpoints (authorize / token / JWKS /
logout) and the issuer are resolved automatically — no per-provider URL
templating. Provider differences (claim names, scopes) are config; **presets**
fill those in for you.

It auto-registers as the application's auth provider. Browser users are
redirected to the IdP's hosted login; mobile/API clients send a bearer token
which is validated against the provider's JWKS when `api_audience` is configured.

## Install

Add to your app's `pyproject.toml` dependencies instead of another auth provider
(e.g. `simple_module_users` / `simple_module_keycloak` — only one auth provider
can be active):

```toml
dependencies = [
    "simple_module_oidc==0.0.42",
]
```

Run `uv sync --all-packages` to install.

## Usage

Select `SM_AUTH_PROVIDER=oidc` explicitly. Keep `Auth` enabled; `Settings` UI
is optional. Exclude Users-dependent modules when selecting this provider.

## Keycloak through the generic preset

This is the primary worked example. The dedicated `keycloak` module is an
alternative; this configuration uses `oidc` throughout.

Create an OpenID Connect client in the Keycloak realm:

- Enable client authentication (a confidential client) and the standard flow.
- Set the valid redirect URI to `<app>/api/oidc/auth/callback`.
- Set the valid post-logout redirect URI to `<app>/oidc/logged-out`.
- Require PKCE with code challenge method **S256**.
- Ensure the realm role mapper includes `realm_access.roles` in ID tokens.
  Assign the intended realm roles to users and include the roles client scope
  in the client's default scopes. Set the username mapper to include
  `preferred_username` in ID tokens.

Use the realm's discovery document and the client's credentials:

```dotenv
SM_AUTH_PROVIDER=oidc
SM_OIDC_PROVIDER=generic
SM_OIDC_DISCOVERY_URL=https://<server>/realms/<realm>/.well-known/openid-configuration
SM_OIDC_CLIENT_ID=<confidential-client-id>
SM_OIDC_CLIENT_SECRET=<client-secret>
```

Here `<app>` includes the application's scheme and host, and `<server>` is the
Keycloak server (including any deployment prefix). Discovery is exactly
`<server>/realms/<realm>/.well-known/openid-configuration` when `<server>` already
includes the scheme. Use HTTPS outside development.

Set these **DB settings** under the `oidc` namespace, using Settings → OIDC when
the Settings UI is enabled:

```json
{
  "roles_claim_path": "realm_access.roles",
  "role_mapping": {"admin": "admin", "user": "user"}
}
```

Choose external roles and app roles appropriate for your host. `role_mapping`
produces application roles; permission grants still come from the framework's
permission registry. No mapping grants `tenant:*` roles. Visit `/oidc/login` to
start sign-in. Cached identity is `(issuer, sub)` with a stable framework UUID.

## Native Microsoft Entra ID

Set the `entra` preset and your single-tenant registration details:

```bash
SM_AUTH_PROVIDER=oidc
SM_OIDC_PROVIDER=entra
SM_OIDC_TENANT_ID=<your-tenant-guid>
SM_OIDC_CLIENT_ID=<app-registration-client-id>
SM_OIDC_CLIENT_SECRET=<client-secret>
```

In the Entra app registration, add the redirect URI:

```
https://<your-host>/api/oidc/auth/callback
```

The `entra` preset derives the discovery URL
(`https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration`),
validates the **id_token**, keys the user cache on **(issuer, `oid`)**, and
maps Entra **app roles** (the `roles` claim) to application roles via
`role_mapping` (default: `admin` and `user` map 1:1). Assign app roles in
*Entra → App registrations → App roles* and *Enterprise applications → Users and groups*.

## Any other OIDC provider

Use the `generic` preset with an explicit discovery URL:

```bash
SM_AUTH_PROVIDER=oidc
SM_OIDC_PROVIDER=generic
SM_OIDC_DISCOVERY_URL=https://<issuer>/.well-known/openid-configuration
SM_OIDC_CLIENT_ID=<client-id>
SM_OIDC_CLIENT_SECRET=<client-secret>
```

## Configuration reference

| Env var | Default | Notes |
|---|---|---|
| `SM_OIDC_PROVIDER` | `generic` | Preset name (`entra`, `generic`). |
| `SM_OIDC_DISCOVERY_URL` | — | Explicit discovery URL; wins over the preset. |
| `SM_OIDC_TENANT_ID` | — | Used by templated presets (Entra) to derive the discovery URL. |
| `SM_OIDC_CLIENT_ID` | — | OAuth client id. |
| `SM_OIDC_CLIENT_SECRET` | — | OAuth client secret. |

Only the five environment variables above bootstrap process wiring and secrets.
These variables seed defaults; explicit DB values can override them.
All other settings are DB-backed; bare environment names and the old claim
mapping environment variables are ignored. Provider, discovery, tenant, client
credentials and JWKS cache TTL changes require a restart. Claim and role mapping
and tenant-claim trust read the live settings state.

| DB setting | Default | Behaviour |
|---|---|---|
| `api_audience` | empty | Bearer authentication disabled until configured; ID tokens always use `client_id`. |
| `trust_tenant_claim` | false | Opt in only to a trusted, validated `tenant_id` claim. Entra `tid` never selects an application tenant. Membership resolution stays authoritative. |
| `scope` | preset | Entra requests `openid email profile offline_access`. |
| `uid_claim` | `oid` for Entra, otherwise `sub` | Required identity claim; there is no fallback. Identities use unique (issuer, subject) UUID mappings. |
| `username_claim` / `name_claim` | `preferred_username` / `name` | Display name with fallback. |
| `email_claim` | `email` | Display email; only generic OIDC literal `email_verified=true` attests ownership. Entra never attests it. |
| `roles_claim_path` | `roles` for Entra, otherwise empty | Dotted claim path to role list. |
| `role_mapping` | admin/user map to themselves | External roles to application roles; `tenant:*` roles are filtered on login and restored sessions. |
| `login_redirect_url` | `/dashboard/` | Blank values normalize to the default. Saved deep links must be local paths. |
| `jwks_cache_ttl_seconds` | 3600 | Last-good signing keys retained on outage; unknown keys share a 30-second fetch cooldown. |

## Login, sessions and logout

Entra supports a single tenant GUID. `common`, `organizations` and `consumers`
are rejected. Unknown presets are validation errors. Discovery requires an issuer
matching the configured discovery URL and HTTPS outside development; different
endpoint hosts are supported. Discovery failure refuses boot outside development;
development retries lazily on login.

Authorization uses code flow with S256 PKCE, state and constant-time nonce
validation. JWTs require `iss`, `sub`, `aud`, `exp` and `iat`, RS256 and the
expected audience. Additional audiences are rejected unless explicitly trusted by
the validator, and a supplied `azp` must name the client (required with multiple
audiences). The returned access token is unused, so `at_hash` is intentionally
not checked.

Sign-in replaces user-bound session state and rotates CSRF. The cookie never
stores the ID token; it stores the ID-token expiry and an encrypted refresh token
when supplied. Expired or unbounded sessions renew using a fresh ID token, with
the same issuer and configured subject required. Definitive refresh rejection
clears authentication. Providers that do not return an `id_token` on refresh
sign the user out at expiry. Transport failures, 5xx and retryable 4xx preserve the
expired session for another attempt, while this request stays unauthenticated.

Logout always clears local state. The optional discovered logout endpoint gets
`client_id` and `post_logout_redirect_uri`, without `id_token_hint`. Register
`https://<your-host>/oidc/logged-out` as the post-logout URI. Providers requiring
an ID-token hint may show a confirmation prompt or leave their SSO session active;
the local signed-out page never automatically signs in.

The host migration `c9d2e4f6a810` (`oidc@head`, #192) creates the identity cache.
Apply host migrations with `upgrade heads` before deployment.

## Activation

Add `simple_module_oidc` to the host's `pyproject.toml` dependencies and
`[tool.uv.sources]`, remove the competing provider, then `uv sync --all-packages`.
Alternatively scope active modules with `SM_MODULES_ENABLED`.

See [the full configuration reference](../../docs/modules/oidc.md)
for every setting, its environment support, tenancy policy and deployment limits.
