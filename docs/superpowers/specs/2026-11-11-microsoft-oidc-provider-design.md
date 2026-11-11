# Microsoft sign-in over OpenID Connect, with PKCE and nonce (#876)

## Goal & scope

The `users` Microsoft provider signs in with OAuth2 + Graph `/me` (`id`,
`userPrincipalName`). It never sees an ID token, never checks the signed-in
account's tenant, and the generic callback hands providers only the access
token, with no session-bound place for a PKCE verifier or nonce.

In scope:
1. The generic callback passes the **whole token response** to
   `OAuthProvider.get_identity`, and keeps a per-login PKCE verifier and OIDC
   nonce in the session next to the state (generic plumbing; a provider opts in).
2. Microsoft becomes OIDC: authorization-code + PKCE (S256) + nonce, scopes
   `openid profile email`, and a validated ID token (RS256 against Entra's JWKS,
   exact issuer, `aud` = client id, `azp`, `exp`/`iat`, `nonce`), reusing
   `auth.oidc_common.jwks.JWKSCache`. A GUID tenant requires `tid` to equal it.
3. Graph is no longer used for sign-in (no `User.Read` scope).

Out of scope: the generic `oidc` provider keeps its current userinfo flow (it
can opt in to the new plumbing later); storing the profile (#877), trusted
email domains (#878), a development discovery override for a local IdP (#879).

## Approach

Microsoft's v2.0 endpoints are fixed per tenant segment
(`https://login.microsoftonline.com/<tenant>/oauth2/v2.0/{authorize,token}`,
JWKS `…/discovery/v2.0/keys`, issuer `…/<tid>/v2.0`), so the provider builds
them from `oauth_microsoft_tenant` with no network call at boot. They sit in
one small endpoints object that #879 can later fill from a discovery document.

Rejected:
- Discovery at client construction (`httpx_oauth`'s `OpenID`, as the generic
  provider does): a synchronous fetch on every boot and settings reload, and a
  Microsoft outage would disable the provider until the next reload.
- Keeping Graph and adding the ID token on top: two identity sources that can
  disagree; the issue asks for Graph to be optional.

## Design

- `users/oauth/providers.py`: `OAuthProvider` gains
  `authorization_url(callback, state, login) -> str` and
  `get_identity(token, login) -> tuple[str, str | None, bool]`, where `login`
  carries the per-login `code_verifier` and `nonce` (both `None` for providers
  that do not use them). Google/GitHub/OIDC behave exactly as today, reading
  `token["access_token"]`.
- `users/oauth/microsoft.py` (new): the OIDC client (a `BaseOAuth2` on the
  tenant's endpoints) and ID-token validation.
  - **Issuer.** GUID tenant: one `JWKSCache` with issuer
    `https://login.microsoftonline.com/<GUID>/v2.0`, and `tid` must equal the
    GUID. `common` / `organizations` / `consumers`: the issuer is built from the
    token's `tid` and validated exactly; one `JWKSCache` per `tid` in a small
    bounded LRU. `organizations` refuses the consumer tenant
    (`9188040d-…`); `consumers` accepts only it.
  - **Account id** (`OAuthAccount.account_id`): unchanged in value so existing
    links keep working. For work/school accounts the Graph `id` *is* the `oid`
    claim. For personal accounts Graph returns a 16-hex id, which the ID token
    carries as the last 16 hex digits of `oid` (`00000000-0000-0000-xxxx-xxxxxxxxxxxx`).
  - **Email** = `preferred_username` (for a member, the UPN Graph returned
    before; for a guest, their home address). Proof stays #873's policy:
    verified only with `oauth_microsoft_trust_tenant_upn` and a GUID tenant, a
    `tid` equal to it, no `idp` claim (Entra sets `idp` for guests and other
    external identities) and no `#EXT#` in the value.
- `users/oauth/api.py`: `begin()` asks the provider whether it uses PKCE/nonce;
  if so it generates both and stores them in the session under
  `oauth_login:<provider>` next to the state. The callback compares the state
  first, then pops the state and login data together (a forged reply cannot
  consume a pending login), passes the verifier to the token exchange and the
  login data to `get_identity`. A failed ID-token check is `OAUTH_PROVIDER_ERROR`.
- Docs: users README, `docs/modules/users.md` (provider table, redirect URI
  unchanged, Entra app registration needs the `openid profile email` delegated
  permissions instead of Graph `User.Read`), CHANGELOG with a **behaviour
  change** note.

## Decisions made

- Fixed Entra endpoints, not discovery (see Approach).
- Account id kept Graph-compatible rather than switching to raw `oid` or `sub`,
  so no data migration and no broken links.
- `preferred_username` as the email, matching what Graph's UPN gave members;
  the optional `email` claim is ignored for now (#877/#878 revisit the profile).
- Guest detection by the `idp` claim, keeping the `#EXT#` check as well.
- PKCE + nonce only for Microsoft in this PR; the plumbing is generic.

## Testing

- Unit (`tests/oauth/providers/`): ID-token validation with a locally generated
  RSA key and JWKS (respx or a fake fetch): good token; wrong `aud`, `iss`,
  `nonce`, expired, bad signature, missing `tid`/`oid`; GUID tenant with another
  `tid`; `organizations` + consumer `tid`; `common` per-`tid` issuer; account-id
  mapping for work and personal `oid`; trust rule with and without `idp`.
- Flow (`tests/oauth/flow/`): `begin()` puts `code_challenge` (S256) and
  `nonce` in the authorize URL and the session; callback passes the verifier to
  the token exchange; a reply with a wrong state leaves the pending login
  intact; existing provider flows unchanged.
- No browser QA: no Entra tenant locally (#879 adds a local-IdP path).

## Risks

- The personal-account id mapping is from Microsoft's published `oid` format,
  not tested against a live personal account here. If it were wrong, an
  existing personal-account link would not be found and that user would be
  refused (`OAUTH_USER_ALREADY_EXISTS`) instead of silently linked elsewhere.
- **Behaviour change** for operators: the Entra app registration must allow
  the `openid`, `profile`, `email` delegated permissions (usually granted by
  default). Graph `User.Read` is no longer requested.
