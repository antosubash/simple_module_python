# Warn about the legacy broker variables only when SM_REDIS_URL can replace them (#868)

## Goal & scope

`warn_on_legacy_redis_vars` tells every deployment that sets
`SM_BG_TASKS_BROKER_URL` / `SM_BG_TASKS_RESULT_BACKEND` to use `SM_REDIS_URL`
instead. `SM_REDIS_URL` seeds *both* fields with one Redis URL, so the advice
only works when the value is a Redis URL. A production host that runs tasks
in-process must set `memory://` + `cache+memory://` (the localhost refusal
blocks the defaults, and no single URL is valid for both), and gets two
warnings on every boot that it cannot act on.

In scope: warn only for a value `SM_REDIS_URL` could express; tests; docs;
CHANGELOG.
Out of scope: changing the production localhost refusal or eager-mode
defaults.

## Approach

Chosen: a legacy variable is warned about only when its value uses a Redis
scheme: `redis` or `rediss`. `SM_REDIS_URL` is also read by the rate limiter,
leases and the invalidation transport through redis-py's `from_url`, so it can
carry only a scheme both Celery and redis-py accept. Celery's `redis+socket` and
`sentinel` fail in redis-py (found in review, round 1 pass 3; the approved design
listed them). Any other scheme (`memory://`, `cache+memory://`, `amqp://`,
`rpc://`, `sqs://`, `db+…`) stays quiet. Those variables are the only way to express such
a value, so they are not really deprecated for it.

Rejected:
- Skip the localhost refusal when `task_always_eager` is on, or default to
  in-process transports. That is a behaviour change to a production guard, and
  `broker_url` is read by more than the task runner (the worker, beat, the
  health check). It doesn't fit a warning fix.
- Silence only `memory://` and `cache+memory://`. That still nags RabbitMQ or
  SQS hosts with advice they cannot follow.

## Design

`modules/background_tasks/background_tasks/core/settings_env_checks.py`:
- add `_REDIS_SCHEMES = frozenset({"redis", "rediss"})`;
- in `warn_on_legacy_redis_vars`, skip a variable whose value's scheme (the text
  before `://`, lowercased) is not in that set;
- extend the docstring with the reason;
- reword the production localhost error so it calls the variables deprecated
  only for a Redis URL, and say they stay the way to set any other transport.

Also reworded to match: the `settings.py` module docstring and the
`SM_BG_TASKS_BROKER_URL (deprecated)` mention in `docs/framework/invalidation.md`.

## Decisions made

- The check is per variable. A host with a Redis broker and an `rpc://` backend
  still gets the warning for the broker, which it can move to `SM_REDIS_URL`.
- No new setting and no new log line.
- Docs: a paragraph in `docs/reference/env-vars.md` § Background tasks saying the
  two variables stay the way to set non-Redis transports (the in-process pair
  for a production host with no Redis), and warn only for Redis URLs.
- CHANGELOG `## [Unreleased]` → Fixed, citing #868.

## Testing

`modules/background_tasks/tests/core/settings/test_background_tasks_redis_url.py`:
- the in-process pair (`memory://` + `cache+memory://`) under
  `SM_ENVIRONMENT=production` boots and logs no deprecation warning;
- an `amqp://` broker logs no warning;
- `rediss://` and an upper-case `REDIS://` still warn; `sentinel://` and
  `redis+socket://` do not (parametrized);
- the existing tests (`redis://` legacy values warn, `SM_REDIS_URL` alone is
  quiet) stay green.

No browser QA: settings-only change (`--skip-browser`).

## Risks

Low. A deployment using `redis://` keeps the warning. Only hosts that cannot
follow the advice stop seeing it.
