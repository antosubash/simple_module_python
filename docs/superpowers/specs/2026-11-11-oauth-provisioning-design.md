# Provider-scoped SSO provisioning, independent of `allow_signup` (#874)

## Goal & scope

Let a site provision accounts on first sign-in through chosen OAuth providers
("staff sign in with the organisation's IdP and get an account") while local
email/password registration stays closed. Today the OAuth callback creates an
account only when `allow_signup` is on, and that switch also opens
`POST /api/users/auth/register`, `/users/register`, the "Sign up" links and the
`user` role for provisioned accounts.

In scope: two `UsersSettings` fields, the callback's create gate, the role a
provisioned account gets, docs. Out of scope: everything local registration
does (it keeps following `allow_signup` alone), #876–#879.

## Approach

```python
oauth_signup_providers: list[str] = []  # e.g. ["microsoft"]
oauth_signup_default_role: str = ""  # "" = no role; an admin grants one
```

- **Create gate** (`users/oauth/api.py`): a sign-in with no existing account
  proceeds when `allow_signup` is on (unchanged) **or** the provider is in
  `oauth_signup_providers` **and** it proved the email (`email_verified`).
  Otherwise `OAUTH_SIGNUP_DISABLED` as today. A listed provider that did not
  prove the email (Microsoft without #873's trust policy, GitHub with an
  unverified primary) is refused with the same code.
- **Role** (`UserManager.on_after_register`): the callback already marks the
  request as an OAuth registration; it now records the provider name. An
  account created through a listed provider gets `oauth_signup_default_role`
  (none when blank); any other OAuth-provisioned account keeps today's rule
  (`user` role only with `allow_signup` on). Local self-signup unchanged.
- **Validation**: unknown provider names (not `google`, `github`,
  `microsoft`, `oidc`) and `oauth_signup_default_role = "admin"` are rejected
  as field errors; a role name that does not exist at sign-in is logged and the
  account gets no role (same as the missing-`user`-role path today).

Rejected:
- A single boolean "SSO signup on": would provision through every configured
  provider, including ones that never prove email; the issue asks for
  provider scope.
- Giving listed-provider accounts the `user` role by default: the safe default
  with signup closed is "wait for an admin", as today (#543's second line).

## Design

- `users/core/settings.py`: the two fields (group "OAuth provisioning") and a
  validator. The file is at the 300-line cap, so the OAuth provider fields,
  `is_tenant_guid` and their validators move to a new
  `users/core/oauth_settings.py` (`OAuthSettings(DbBackedSettings)` base,
  `UsersSettings` inherits it); public names stay importable from
  `users.core.settings`.
- `users/oauth/api.py`: gate as above; set the registration flag to the
  provider name instead of `True`.
- `users/accounts/registration.py`: `attach_default_role(session, user,
  role_name=USER_ROLE_NAME)`; a helper picks the role for a provisioned
  account so `manager.py` (297 lines) stays under the cap.
- Docs: users README, `docs/modules/users.md`, CHANGELOG.

## Decisions made

- Field names from the issue; `oauth_signup_default_role` is `str` with `""`
  meaning none (the settings store handles `str` fields; `None` adds nothing).
- `admin` is refused as the default role: auto-granting full admin to a
  provider's users is never what an operator means.
- When `allow_signup` is on **and** the provider is listed, the listed-provider
  rule wins (verified email required, `oauth_signup_default_role`), so listing
  a provider never widens what it can do.
- Provider names are validated against the four built-in keys.

## Testing

- Settings: defaults, unknown provider rejected, `admin` role rejected.
- Flow (fake provider, `allow_signup=False`): listed + verified → account
  created, external, gets the configured role / no role when blank; listed +
  unverified → `OAUTH_SIGNUP_DISABLED`; unlisted → refused; `allow_signup=True`
  + unlisted → `user` role as today; listed with a missing role → no role, warning.
- Local `/api/users/auth/register` and `/users/register` still 404/refuse with
  `allow_signup=False` while a provider is listed.
- No browser QA (backend-only).

## Risks

- Moving the OAuth fields to a base class changes field order in the settings
  editor; groups keep their names, so the form still groups them. If the
  editor orders by declaration, the OAuth groups move up — acceptable.
