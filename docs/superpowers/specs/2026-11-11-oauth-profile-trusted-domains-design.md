# OAuth identity profile and trusted email domains (#877, #878)

## Goal & scope

**#877.** An OAuth sign-in keeps only `oauth_name`, `account_id`,
`account_email` and tokens. Store the IdP's profile so administrators can see
which identity an account belongs to and a provider that changes its key has
something to migrate from, and use the IdP's name for the account.

**#878.** Email trust is all-or-nothing per provider. Let an operator trust
addresses on domains their organisation owns, per provider, and nothing else.

Both change what a provider returns from `get_identity`, so they ship together.
Out of scope: changing the account email from the IdP (unique-email
collisions), #879's local IdP.

## Approach

`OAuthProvider.get_identity` returns an `OAuthIdentity` (frozen dataclass)
instead of a 3-tuple: `account_id`, `email`, `email_verified`, `subject`,
`username`, `display_name`, `extra` (small dict of provider-specific ids). The
callback applies trusted domains to it, runs the existing find-or-create, then
writes the profile onto the linked `OAuthAccount`.

Rejected: a separate `users_oauth_identity` table (the link row already is one
per identity), and a single global domain list (a domain trusted for Microsoft
must not become trusted for GitHub).

## Design

### Profile (#877)

- `OAuthAccount` gains nullable `subject` (320), `username` (320),
  `display_name` (320), `extra` (JSON), `last_sign_in_at` (`AwareDateTime`).
  One migration on the users trunk (`--head users@head`); no backfill.
- Each provider fills the profile from what it already fetches:
  OIDC: `sub`, `preferred_username`, `name`; Google: `resourceName`, primary
  address, `names[0].displayName`; GitHub: `id`, `login`, `name`; Microsoft:
  `sub`, `upn`/`preferred_username`, `name`, `extra = {oid, tid}`.
- After `oauth_callback`, the callback updates the link row (same request
  session, committed by the middleware) and stamps `last_sign_in_at`.
- `User.full_name`: set from `display_name` when the callback creates the
  account; on later sign-ins only when the new `oauth_sync_profile` setting is
  on (default off), and never to an empty value. The email is never changed.
- Admin **Edit user** page: a "Linked sign-ins" section listing provider,
  username, subject and last sign-in per link (read-only). New `en.json` keys;
  `make gen-i18n` and `make gen-api-types`.

### Trusted email domains (#878)

- `oauth_trusted_email_domains: dict[str, list[str]] = {}`, e.g.
  `{"microsoft": ["iiasa.ac.at"]}`; keys validated against the provider names,
  domains lowercased and IDNA-normalised, no wildcards.
- The email becomes verified only when its domain is listed **exactly** for
  that provider (no subdomains) **and** the provider's own identity checks
  pass. For Microsoft that means a GUID tenant equal to `tid`, no foreign
  `idp`, no `#EXT#` (the #873 member checks without requiring the UPN trust
  flag); for Microsoft the address is the `email` claim on a listed domain,
  else `upn`/`preferred_username` on a listed domain. Other providers: the
  address they returned.
- A domain listed for Microsoft while the tenant is not a GUID logs
  `users.oauth.trusted_domains_ignored` and has no effect.

## Decisions made

- One PR for both issues (shared `OAuthIdentity`).
- `oauth_sync_profile` default off; `full_name` only, never the email.
- A listed domain is the operator's statement, so for Google, GitHub and OIDC
  it makes the returned address verified even when the provider gave no
  proof; Microsoft additionally needs the member checks, because its claims
  are editable by the tenant.
- `extra` is limited to Microsoft's `oid`/`tid` for now.

## Testing

- Unit: each provider's `OAuthIdentity`; domain matching (case, IDNA,
  subdomain refused, other provider's list ignored); Microsoft email choice.
- Flow: profile columns written on create and on later sign-in;
  `last_sign_in_at` stamped; `full_name` set on create, synced only with the
  setting; a listed domain links a verified local account; a guest on a
  listed domain does not.
- Migration: `make doctor`, `alembic check` (CI), Postgres round trip (CI).
- Admin page: Vitest for the "Linked sign-ins" section; a browser check of the
  Edit page with a seeded link.

## Risks

- `oauth_callback` (fastapi-users) owns the link-row write; the profile update
  runs after it in the same session. If a future fastapi-users version changes
  that, the update still works (it looks the row up by provider and account id).
