# Plan: provider-scoped SSO provisioning (#874)

Design: `docs/superpowers/specs/2026-11-11-oauth-provisioning-design.md`. Sequential tasks.

1. **Split OAuth settings** — move every `oauth_*` field, `is_tenant_guid` and the
   Microsoft-trust validator from `users/core/settings.py` into
   `users/core/oauth_settings.py` (`OAuthSettings(DbBackedSettings)`); `UsersSettings`
   inherits it; `users/oauth/providers.py` imports from the new module. Done: users
   tests green with no behaviour change.
2. **New settings** — `oauth_signup_providers`, `oauth_signup_default_role` with field
   validators (known provider names; not `admin`). Test first:
   `tests/oauth/providers/test_users_oauth_signup_settings.py`.
3. **Create gate** — `users/oauth/api.py`: listed + verified provider may create with
   `allow_signup` off; registration flag carries the provider name. Test first:
   `tests/oauth/flow/test_users_oauth_provider_signup.py`.
4. **Role** — `attach_default_role(..., role_name)` and a helper choosing the role for an
   OAuth-provisioned account; `on_after_register` uses it. Tests in the same flow file
   (configured role, blank, missing role, unlisted + `allow_signup=True` → `user`).
5. **Local registration stays closed** — test `/api/users/auth/register` and
   `/users/register` refuse with a provider listed and `allow_signup=False`.
6. **Docs** — users README, `docs/modules/users.md`, CHANGELOG.
7. **Full check** — `make lint`, users tests; full suites in `/vf`.
