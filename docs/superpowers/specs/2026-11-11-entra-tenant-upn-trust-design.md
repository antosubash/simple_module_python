# Trusted single-tenant UPN policy for Microsoft sign-in (#873)

## Goal & scope

With the `users` provider, Microsoft (Entra) sign-in can never prove an email
(`get_identity` always returns `email_verified=False`), so on a site with
self-signup closed nobody can sign in with Microsoft: a verified local account
or pending invite with the same email is refused (`OAUTH_USER_ALREADY_EXISTS`),
and a new account is refused (`OAUTH_SIGNUP_DISABLED`).

In scope: an opt-in setting that, for a single pinned tenant, treats a member
account's `userPrincipalName` as a verified email, so it links to an invited or
verified local account and new accounts start verified.

Out of scope (separate issues): provisioning independent of `allow_signup`
(#874), OIDC-based Microsoft provider with validated `oid`/`tid` claims (#876),
storing the IdP profile (#877), trusted email domains (#878), a dev discovery
override (#879).

## Approach

Add `oauth_microsoft_trust_tenant_upn: bool = False` to `UsersSettings`
(group "Microsoft OAuth"). `build_clients` resolves the policy once: it is
**effective** only when the setting is on and `oauth_microsoft_tenant` is a
canonical work/school tenant GUID (`is_tenant_guid`). `OAuthProvider` gains a `trust_email: bool = False` field (the
NamedTuple stays positional-compatible), and Microsoft's `get_identity` returns
`(graph id, UPN, True)` when `trust_email` is set, the id and UPN are non-empty,
and the UPN has no `#EXT#` (case-insensitive). Everything else stays `False`.

Rejected:
- Trust `mail` instead of UPN: `mail` is user-/admin-editable and not
  domain-verified; the issue explicitly says never `mail`.
- Wait for #876 (validated `tid` claim): the Graph flow is already pinned to the
  tenant by the authorize/token endpoint (`login.microsoftonline.com/<GUID>`),
  so a token can only come from that tenant; #876 can add a `tid` check later
  without changing this setting.

## Design

- `users/core/settings.py`: the field, plus a `model_validator` that logs
  `users.oauth.microsoft_trust_ignored` (WARNING) when the setting is on and the
  tenant is `common`/`organizations`/`consumers` (or its GUID)/any non-canonical-GUID. Not an error: a
  settings edit in the admin UI must not fail, and the safe behaviour (no trust)
  is what applies.
- `users/oauth/providers.py`: `OAuthProvider.trust_email`; the helper
  `is_tenant_guid(tenant)` lives in `core/settings.py` (the settings validator and
  `build_clients` both use it); Microsoft branch of `get_identity` as above.
- No change to `api.py`: `email_verified` already drives `associate_by_email`
  and `is_verified_by_default`, the `_unproven_account` guard (unverified,
  un-invited local account → `OAUTH_ACCOUNT_NOT_VERIFIED`) and the
  `allow_signup` gate stay as they are.
- Docs: `modules/users/README.md`, `docs/modules/users.md` (settings table +
  provider table + a short "Signing in pre-approved staff" note), CHANGELOG.

## Decisions made

- Setting name from the issue (`oauth_microsoft_trust_tenant_upn`), default off.
- GUID check via `uuid.UUID(...)`, restricted to the canonical hyphenated form
  (case-insensitive) and excluding the `consumers` tenant's fixed GUID
  (`9188040d-6c67-4c5b-b112-36a304b66dad`, personal accounts); verified-domain
  names (`contoso.onmicrosoft.com`) as tenant are **not** trusted, since the
  issue scopes trust to a GUID.
- `#EXT#` match is case-insensitive; an empty id or UPN is never trusted.
- Warning at settings validation (boot and every settings reload), not a
  doctor code.

## Testing

- Unit (`tests/oauth/flow/test_users_oauth_provider_identity.py`): member UPN
  trusted with a GUID tenant; guest `#EXT#` UPN, empty id/UPN, setting off,
  and `common`/`organizations`/domain tenant all stay unverified.
- Settings: warning logged for non-GUID tenant with trust on; silent otherwise.
- Flow (`test_users_oauth_*` style, fake Microsoft client): with the policy on
  and `allow_signup=False`, an invited account and a verified local account
  both sign in and get linked; an unverified, un-invited local account is still
  refused; guest UPN is still refused.
- No browser QA (backend-only; no Entra tenant available locally).

## Risks

- A UPN is not always the user's mail address (UPN `j.doe@corp.com` vs invite
  sent to `jane@corp.com`): the invite then doesn't match and the user is
  refused as before. Documented; #878 (trusted domains) and #877 cover more.
