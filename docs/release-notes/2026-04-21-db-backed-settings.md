# DB-backed module settings

Every `SM_<MODULE>_*` env var has moved to the admin UI at `/settings/modules`.
`.env` now only needs `SM_DATABASE_URL` in typical deployments.

## Upgrading

After deploying this release:

1. Run `uv run sm-settings import-from-env` once to seed the DB with your current environment values.
2. Remove the `SM_<MODULE>_*` entries from your `.env` / deployment config (they're no longer read).

## Breaking changes

Setting `SM_USERS_ALLOW_SIGNUP=true` (or any other `SM_<MODULE>_*`) in the environment no longer has any effect. Use the admin UI or the `sm-settings` CLI.
