# Plan: OAuth identity profile + trusted email domains (#877, #878)

Design: `docs/superpowers/specs/2026-11-11-oauth-profile-trusted-domains-design.md`. Sequential.

1. `users/oauth/identity.py`: `OAuthIdentity`, `normalize_domain`, `email_on_domains`. Unit tests.
2. Settings (`users/core/oauth_settings.py`): `oauth_trusted_email_domains` (validated, normalised),
   `oauth_sync_profile`; warning when Microsoft domains are listed without a GUID tenant.
3. Providers return `OAuthIdentity` with subject/username/display_name/extra; generic providers apply
   their trusted domains; Microsoft chooses `email` → `upn`/`preferred_username` on a listed domain and
   needs the member checks. Update provider/flow tests.
4. `OAuthAccount` columns + migration (`--head users@head`); `users/oauth/profile.py` writes the
   profile and `last_sign_in_at` after `oauth_callback`, sets/syncs `full_name`. Flow tests.
5. Admin Edit page: `linked_sign_ins` prop (`admin/queries.py`), `LinkedSignInsCard.tsx`, en.json keys,
   gen-i18n; Vitest.
6. Docs (README, docs/modules/users.md), CHANGELOG; `make lint`, `make doctor`, users tests.
