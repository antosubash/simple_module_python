# OIDC

`simple_module_oidc` is the generic OpenID Connect auth provider (#192).
It discovers authorization, token, JWKS and optional logout and revocation endpoints. It uses
hosted login with authorization code flow, S256 PKCE, state and nonce checks.
Only one auth provider may be active; select it with `SM_AUTH_PROVIDER=oidc`.

## Install and activate

Add `simple_module_oidc` to your host dependencies (and a workspace source
when developing in this repository), then sync your environment. Keep `Auth`
enabled. `Settings` is optional: its UI edits DB-backed policy, but framework
settings hydration works without it. Exclude modules that require `Users` when
selecting OIDC, because discovery removes competing auth providers. Use
`SM_MODULES_ENABLED` if you need an explicit module set.

Apply host migrations with `make migrate` (`alembic upgrade heads`). Revision
`c9d2e4f6a810` creates `oidc_user_cache` on the new independent `oidc` branch.
A host consuming the package must include this migration in its own history;
module packages do not run migrations themselves.

## Keycloak through the generic preset

This is the primary worked example. The dedicated `keycloak` module is an
alternative; this configuration uses `oidc` throughout.

Create an OpenID Connect client in the Keycloak realm:

- Enable client authentication (a confidential client) and the standard flow.
- Set the valid redirect URI to `<app>/api/oidc/auth/callback`.
- Set the valid post-logout redirect URI to `<app>/oidc/logged-out`.
- Require PKCE with code challenge method **S256**.
- Add realm roles to the **ID token**. Keycloak 26 puts `realm_access.roles`
  only in the access token by default, and this module reads roles from the ID
  token. Under Client scopes -> `roles` -> Mappers -> `realm roles`, turn on
  **Add to ID token** (token claim name `realm_access.roles`, multivalued), or
  add a **User Realm Role** mapper with those settings to the client's
  dedicated scope. Then assign the intended realm roles (for example `admin`)
  to users.
- Keep the default `profile` and `email` client scopes: they supply
  `preferred_username`, `name`, `email` and `email_verified` in the ID token.

Use the realm's discovery document and the client's credentials:

```dotenv
SM_AUTH_PROVIDER=oidc
SM_OIDC_PROVIDER=generic
SM_OIDC_DISCOVERY_URL=https://<server>/realms/<realm>/.well-known/openid-configuration
SM_OIDC_CLIENT_ID=<confidential-client-id>
SM_OIDC_CLIENT_SECRET=<client-secret>
SM_OIDC_ROLES_CLAIM_PATH=realm_access.roles
```

`SM_OIDC_ROLES_CLAIM_PATH` seeds the roles path, so the first Keycloak admin is
mapped to `admin` on their first sign-in. Without it nobody holds `admin`, and
the Settings UI that edits the path needs one. A value saved in the UI later
wins over the variable.

Here `<app>` includes the application's scheme and host, and `<server>` is the
Keycloak server (including any deployment prefix). Discovery is exactly
`<server>/realms/<realm>/.well-known/openid-configuration` when `<server>` already
includes the scheme. Use HTTPS outside development.

Set these **DB settings** under the `oidc` namespace, using Settings → OIDC when
the Settings UI is enabled:

```json
{
  "role_mapping": {"admin": "admin", "user": "user"}
}
```

Choose external roles and app roles appropriate for your host. `role_mapping`
produces application roles; permission grants still come from the framework's
permission registry. No mapping grants `tenant:*` roles. Visit `/oidc/login` to
start sign-in. Cached identity is `(issuer, sub)` with a stable framework UUID.

## Presets and Microsoft Entra ID

`generic` requires an explicit discovery URL. Its defaults are `sub`,
`preferred_username`, `email`, `name`, no roles path, and scope
`openid email profile`. Use dotted paths such as `realm_access.roles` or
`resource_access.my-client.roles` to select a list of external roles; a claim
named exactly like the path wins, so Auth0/Okta URL-namespaced claims such as
`https://example.com/roles` work as written. Keycloak issues refresh tokens for
this scope; Auth0 and Okta only do with `offline_access`, so add it to `scope`
there or sessions end at ID-token expiry.

`entra` supports **single-tenant** registrations. Register a Web application
for accounts in your directory, create its client secret, and add
`<app>/api/oidc/auth/callback` as the redirect URI. Configure:

```dotenv
SM_AUTH_PROVIDER=oidc
SM_OIDC_PROVIDER=entra
SM_OIDC_TENANT_ID=<directory-tenant-guid>
SM_OIDC_CLIENT_ID=<application-client-id>
SM_OIDC_CLIENT_SECRET=<client-secret>
```

The preset derives
`https://login.microsoftonline.com/<tenant>/v2.0/.well-known/openid-configuration`.
It requests `openid email profile offline_access`: `offline_access` allows a
refresh token so the app can renew expired browser sessions. Define app roles
under App registrations → App roles and assign them under Enterprise
applications → Users and groups. The preset reads the `roles` claim and maps
it through `role_mapping` (default `admin`/`user` map to themselves).

Entra uses the required `oid` identity claim, namespaced by the exact issuer
(which identifies the directory). A changed pairwise `sub` does not change that
identity. `tid` is an Entra directory identifier, never an application tenant.
`common`, `organizations`, `consumers` and templated discovery issuers are
rejected. There is no multi-directory issuer substitution. Entra email claims
are display data and do not attest verified mailbox ownership.

## Configuration reference

All rows name fields of `OidcSettings`, stored as `oidc.<field>`. The six
`SM_OIDC_*` variables below seed bootstrap defaults (process wiring, secrets
and the first admin's roles path); explicit DB values can
override them. **— means no environment variable**, not an undocumented `SM_OIDC_*` spelling.
Bare environment variables and old claim-mapping environment variables are
ignored. Host selection `SM_AUTH_PROVIDER=oidc` is a separate host setting.

| Setting | Environment variable | Default | Meaning |
|---|---|---|---|
| `provider` | `SM_OIDC_PROVIDER` | `generic` | `generic` or `entra`; unknown presets fail validation. Restart required. |
| `discovery_url` | `SM_OIDC_DISCOVERY_URL` | empty | Explicit discovery URL, taking precedence over preset derivation. Restart required. |
| `tenant_id` | `SM_OIDC_TENANT_ID` | empty | Entra directory GUID used to derive discovery. Restart required. |
| `client_id` | `SM_OIDC_CLIENT_ID` | empty | Browser ID-token audience and OAuth client ID. Restart required. |
| `client_secret` | `SM_OIDC_CLIENT_SECRET` | empty | Confidential-client secret, masked by settings handling. Restart required. |
| `api_audience` | — | empty | Expected API JWT audience; empty disables bearer authentication. |
| `api_allowed_client_ids` | — | empty | Clients besides `client_id` allowed to call the API (`azp`/`appid`). |
| `trust_tenant_claim` | — | `false` | Whether a validated `tenant_id` claim may select an app tenant; see below. |
| `scope` | — | preset | Generic: `openid email profile`; Entra adds `offline_access`. |
| `uid_claim` | — | preset | Generic `sub`; Entra `oid`. Required; no fallback. Changing it changes identity mapping. |
| `username_claim` | — | `preferred_username` | Display name first choice. |
| `email_claim` | — | `email` | Display email. Generic literal `email_verified=true` alone supplies verification proof. |
| `name_claim` | — | `name` | Fallback display name. |
| `roles_claim_path` | `SM_OIDC_ROLES_CLAIM_PATH` | preset | Generic empty; Entra `roles`; dotted path to a list. |
| `login_redirect_url` | — | `/dashboard/` | Local destination after login when no safe saved deep link exists; blanks normalize to default. |
| `jwks_cache_ttl_seconds` | — | `3600` | Nonnegative signing-key cache TTL. Restart required. Last-good keys survive outages; unknown keys share a 30-second fetch cooldown. |
| `role_mapping` | — | `{"admin":"admin","user":"user"}` | External roles to application roles. Unmapped roles and mapped `tenant:*` roles are discarded. |

Claim and role policy reads current module state after hydration/reload. Mapping
changes affect fresh tokens (callback, bearer, refresh); roles already in a
browser session remain until refresh. Tenant-claim trust is rechecked on each
restored session. Discovery, clients and JWKS initialize together, so fields
marked restart-required need a process restart rather than a partial reload.

## Bearer APIs and tenancy

Set the DB setting `api_audience` to the audience issued for your API. Send the
API JWT in `Authorization: Bearer <token>` (scheme is case insensitive). Browser
ID tokens always validate against `client_id`; they do not authorize a distinct
API audience. Bearer requests use the framework's bearer auth kind and cannot
manage API tokens. PAT/service-token handling stays with its owning resolver.
The returned OAuth access token from browser code exchange is unused.

An API token is accepted only from a known client: its `azp` (or `appid` on
Entra v1 tokens) must be `client_id` or listed in the DB setting
`api_allowed_client_ids`. List each SPA, CLI or service that calls the API; a
token naming no client is refused. Scopes (`scp`) are not checked; what a caller
may do still comes from its mapped roles.

Leave `trust_tenant_claim=false` unless you control and trust the IdP mapper
producing `tenant_id`. When enabled, the claim must pass framework tenant-ID
validation; a registered tenant resolver remains authoritative. Memberships,
not external claims or `role_mapping`, assign `tenant:*` roles. Entra `tid`
never selects an application tenant.

## Sessions, logout and limits

JWT validation requires RS256, signature, exact issuer, subject, audience,
expiry and issued-at. For the browser ID token a supplied `azp` must name this
client and is required for multiple audiences; additional audiences are rejected.
An API access token's `azp` is the calling client: it is not pinned to this
client but checked against `api_allowed_client_ids` (see above).
Discovery validates URLs and issuer, requires HTTPS outside development, and
permits legitimate endpoints on different hosts. Discovery failure refuses boot
outside development; development retries lazily at login.

Authorization endpoints discovered with existing query parameters retain them
when the client adds the authorization parameters (#755).

Login replaces user-bound session state and rotates CSRF. The cookie carries
`oidc_identity` and an `oidc_authority` hash binding it to this provider, issuer
and client ID. Cookies from another authority require sign-in again; legacy
OIDC cookies with their own identity key are stamped on first use (#750).
See [browser session authority](auth.md#browser-session-authority-750). The signed cookie
stores a minimal principal, ID-token expiry, issuer/subject identity and an
encrypted refresh token if issued. It never retains the ID token. At expiry,
refresh must return a valid ID token for the same identity. **Providers that do
not return an `id_token` on refresh sign the user out at expiry.** Parallel requests at expiry serialize through a per-session framework lease
(15-second TTL, at most 3 seconds waiting). Waiters copy the winner's sealed
refresh token, principal and deadline from a shared 30-second DB outcome into
their own cookie; no IdP reuse grace period is needed for this race (#738).
A missing/expired waiter outcome or lease timeout leaves that request's cookie
untouched and signs only that request out. Apply migration `a738c2e4f601` (`auth@head`); see
[auth coordination](auth.md#concurrent-browser-renewal-738). Definitive refresh
rejection clears authentication; network/5xx/retryable failures retain
the expired session for retry while leaving that request unauthenticated; the
token endpoint is not called again for 30 seconds. A refresh token that would push
the session cookie past the 4 KB browser limit is not stored (the warning is
logged), and that session ends at ID-token expiry.

Logout first attempts to revoke the decrypted refresh token when discovery
advertises a `revocation_endpoint`, using `token_type_hint=refresh_token` and the
client authentication the revocation endpoint advertises in
`revocation_endpoint_auth_methods_supported` (falling back to the token
endpoint's). Revocation is best-effort with a 3 second timeout: failures still
clear the local session and continue logout, logging only the failure type,
never the token or response body. Without that endpoint or a usable refresh
token, no revocation request is made. A malformed or non-HTTPS (outside
development) `revocation_endpoint`, or malformed auth-method lists, are ignored
with a warning rather than blocking sign-in.

Logout then clears the local session and uses discovered `end_session_endpoint` with
`client_id` and `post_logout_redirect_uri=<app>/oidc/logged-out`. Inertia logout
uses external navigation. Without that endpoint, logout stays local. There is
**no `id_token_hint`**, so an IdP may prompt for confirmation or retain its SSO
session. The public signed-out landing page does not auto-login. Close the
browser on a shared computer when provider logout cannot be guaranteed.

The access token is not consumed, so **`at_hash` is not checked**. Tokens are
validated with 10 seconds of clock leeway. The client authenticates to the
token endpoint with `client_secret_post` when discovery lists it or omits
`token_endpoint_auth_methods_supported` (OIDC Discovery's default for an omitted
list is `client_secret_basic`; this module keeps the post method it always sent);
otherwise it uses `client_secret_basic`, form-encoding the client ID and secret
before HTTP Basic encoding. An IdP
`error` reply to the callback (for example a cancelled sign-in)
answers 401 once the login state matched. A callback with a spent or unknown
state (browser Back after signing in, or a second tab whose login another tab
finished) sends a signed-in user on to `login_redirect_url` and answers anyone
else with 419, the framework's "expired, sign in again" page. `/oidc/logged-out`
likewise sends a signed-in visitor on to `login_redirect_url`. Entra support
is single-tenant only. The directory lists only users who have signed in,
reads cached names/emails and returns unknown roles (`None`), rather than
claiming no roles. Activity statistics count last login; account creation dates
are unknown. No remote IdP account listing is performed.

## Shared protocol implementation

OIDC and Keycloak use `auth.oidc_common` for JWT validation, refresh-token
sealing, sign-in session rotation, renewal, cache persistence and user
directories (#741). OIDC retains discovery, ID-token-based browser identity,
per-purpose audiences and its API client allowlist. Its issuer/subject identity,
`oidc_user_cache` table, session keys and encryption key derivation are unchanged;
no migration or session conversion is needed.
