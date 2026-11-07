# Plan: warm the invalidation publish connection (GH #880)

Design: `docs/superpowers/specs/2026-11-07-invalidation-warm-publish-design.md`.

1. **Fake-client tests first.** Create `modules/background_tasks/tests/core/invalidation/test_background_tasks_invalidation_warmup.py`.
   - Its own small fake with `ping()`, because the shared fake lives in a 293-line file. Copy only what the tests need.
   - Cover: a ping after subscribe; another after a reconnect; a failing ping and a hanging ping both leave the listener delivering.
   - Done when they fail against `main`.
2. **Implement** `_warm_publish_connection` in `modules/background_tasks/background_tasks/core/invalidation.py` and call it after a successful subscribe. Add one sentence to the `PUBLISH_TIMEOUT_SECONDS` docstring. Done when the step 1 tests pass.
3. **Real-Redis test** in the same new file: once subscribed, `CLIENT LIST` shows a client whose last command is `ping`, and a publish does not add a client. Done when it passes against `SM_TEST_REDIS_URL`.
4. **CHANGELOG** `[Unreleased]` entry under Fixed, citing #880.
5. `make lint`, `make test-py` (with `SM_TEST_REDIS_URL`), `make test-js`.

Tasks 1–3 are sequential and touch the same files; none is marked hard.
