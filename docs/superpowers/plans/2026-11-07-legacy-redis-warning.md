# Plan: warn about the legacy broker variables only for Redis URLs (#868)

Design: `docs/superpowers/specs/2026-11-07-legacy-redis-warning-design.md`.

1. **Tests first** (`modules/background_tasks/tests/core/settings/test_background_tasks_redis_url.py`):
   in-process pair under production is quiet; an `amqp://` broker is quiet;
   `rediss`, `sentinel` and an upper-case `REDIS` scheme still warn; the check
   is per variable. Done when the three quiet/per-variable tests fail on main.
2. **Fix** (`background_tasks/core/settings_env_checks.py`): `_REDIS_SCHEMES`
   and a scheme check in `warn_on_legacy_redis_vars`. Done when the settings
   tests pass.
3. **Docs**: a paragraph under the Background tasks table in
   `docs/reference/env-vars.md`; CHANGELOG Fixed entry citing #868.
4. **Verify**: `make lint`, `make test-py`.

All tasks are sequential and small; none is hard.
