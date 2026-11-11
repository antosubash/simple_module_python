# Plan: trusted single-tenant UPN policy (#873)

Design: `docs/superpowers/specs/2026-11-11-entra-tenant-upn-trust-design.md`.
Tasks run in order (each touches the previous one's files).

1. **Identity rule** — `modules/users/users/oauth/providers.py`.
   Test first in `tests/oauth/flow/test_users_oauth_provider_identity.py`:
   `OAuthProvider(..., trust_email=True)` returns verified for a member UPN;
   `#EXT#` (any case), empty id, empty UPN, `trust_email=False` stay unverified.
   Add `trust_email: bool = False` to `OAuthProvider`, use it in the Microsoft branch.
   Done: new tests pass, existing identity tests unchanged.
2. **Setting + policy resolution** — `users/core/settings.py`, `providers.build_clients`.
   Tests: `build_clients` sets `trust_email` only for setting on + GUID tenant
   (`common`, `organizations`, `consumers`, `contoso.onmicrosoft.com` → False);
   a WARNING `users.oauth.microsoft_trust_ignored` is logged for trust on + non-GUID,
   none otherwise. Done: tests pass, settings.py under 300 lines.
3. **Callback flow** — new `tests/oauth/flow/test_users_oauth_tenant_upn_trust.py`,
   following `test_users_oauth_signup_gate.py`/`..._unverified_link.py` fakes:
   `allow_signup=False` + policy on → invited and verified local accounts sign in and
   link; unverified un-invited account → `OAUTH_ACCOUNT_NOT_VERIFIED`; guest UPN → refused.
4. **Docs** — users README, `docs/modules/users.md`, `CHANGELOG.md` `[Unreleased]`.
5. **Full check** — `make lint`, `make test-py`, `make test-js`.
