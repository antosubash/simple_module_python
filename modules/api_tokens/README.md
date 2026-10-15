# simple_module_api_tokens

Personal access tokens and service API keys for
[simple_module](https://github.com/antosubash/simple_module_python) apps.

- `smpat_…` tokens act for their owner, `smsk_…` service keys act for no one,
  with roles chosen at creation (never `admin`) and a pinned tenant.
- Every token carries **scopes**, which cap what it can do on every request,
  even when its owner is an admin. Demoting the owner shrinks the token at once.
- Only `sha256(token)` is stored, and the secret is shown once. Revocation
  applies on the next request.
- Tokens can only be created, listed and revoked from a signed-in browser
  session, with a CSRF token.

## Install

```bash
pip install simple_module_api_tokens
```

Add `simple_module_api_tokens` to your host's dependencies and generate a
migration. It needs the `auth`, `users` and `settings` modules.

## Usage

```bash
curl -H "Authorization: Bearer smpat_…" https://app.example.com/api/feature_flags/
```

| Route | Page | Purpose |
|---|---|---|
| `GET /api-tokens/` | `ApiTokens/Index` | Your own tokens (`api_tokens.use`) |
| `GET /admin/api-tokens/` | `ApiTokens/Admin` | All tokens and service keys (`api_tokens.manage`) |

Settings: `max_lifetime_days` (default 365), DB-backed.

See [docs/modules/api_tokens.md](https://github.com/antosubash/simple_module_python/blob/main/docs/modules/api_tokens.md)
for the resolution order, the scope cap and the tenancy rules.
