# Sentry

Optional error reporting for the web process and Celery workers. It costs
nothing until you opt in: with `SM_SENTRY_DSN` unset, `init_sentry()` returns
before `sentry_sdk` is imported.

```bash
pip install "simple_module_hosting[sentry]"
export SM_SENTRY_DSN=https://<key>@o0.ingest.sentry.io/<project>
```

| Variable | Default |
|---|---|
| `SM_SENTRY_DSN` | unset (disabled) |
| `SM_SENTRY_ENVIRONMENT` | `SM_ENVIRONMENT` |
| `SM_SENTRY_TRACES_SAMPLE_RATE` | `0.0` |

These are env only: the DSN is a secret and the SDK has to start before the DB
is open. The DSN is never logged.

## Where it starts

- Web: `create_app` calls `init_sentry("web")` before any middleware is built.
- Worker: background_tasks calls `init_sentry("worker")` on `worker_process_init`,
  so every prefork child reports.

## Tags

| Tag | Source |
|---|---|
| `request_id` | the correlation id |
| `tenant` | the request's resolved tenant, or the task's tenant |
| `user_id` | the principal's id (`user.id` is set; never email, username or IP) |
| `module` | top-level package of the route endpoint, or the prefix of `<module>.<task>` |
| `task` | the Celery task name (worker events) |
| `process` | `web` or `worker` |

## Scrubbing

`send_default_pii` is off and local variables are not attached to stack frames
(they hold the ASGI scope). The SDK's own scrubber matches exact key names
only, so `simple_module_hosting.sentry_scrub` runs a stricter pass from both
`before_send` and `before_send_transaction`:

- After targeted passes, *every* event field (tags, `server_name`, threads,
  a top-level `stacktrace`, fields a future SDK adds) goes through the same
  recursive pass: deny by default rather than a list of known fields.
- Any key, at any depth, whose name contains `password`/`passwd`/`pwd`,
  `passphrase`, `secret`, `token`, `authorization`, `cookie`, `session`,
  `api_key`, `csrf`, `credential`, `private_key`, `signature`, `dsn`, `jwt`,
  `bearer`, a card-number word or a client-address word (`forwarded`,
  `real_ip`, `remote_addr`, …), or has a whole-word `auth`, `pass`, `otp`,
  `pin`, `sid`, `sig`, `ssn`, `cvv`, `mfa` (snake, kebab and camelCase:
  `basicAuth`, `DB_PASS`, but not `author`), is replaced with `[Filtered]`.
  `["Authorization", "…"]` pairs in header/query lists count as keys. Such
  request headers are removed outright.
- Request cookies, bodies and `env` (`REMOTE_ADDR`) are dropped; the event
  user is reduced to `{"id": …}`.
- Every string (bytes too) loses `key=value` / `key: value` /
  `"key": "quoted value"` pairs with a sensitive key (escaped JSON included),
  whole `Cookie:`/`Authorization:` header lines, the OAuth `code` query
  parameter, `Bearer`/`Basic`/`Digest` credentials, URL userinfo, JWTs and
  bare 32+ character tokens mixing letters and digits (UUIDs and
  snake_case identifiers excepted; Sentry's own event/trace/span ids are
  kept). Strings over 64 KiB are truncated before scanning.
- Celery task `args`, `kwargs` and return values, SQL `db.params` and frame
  `vars` are dropped wherever they appear.
- URL-sourced transaction names and URL paths have id- and
  token-shaped segments replaced with `*`.
- If scrubbing raises, the event is dropped (only the exception type is
  logged); a half-scrubbed event is never sent.
- Not covered: secrets passed as positional log arguments
  (`log.info("%s", token)`) with nothing marking them as secret, and
  base64 tokens with `/` shorter than 32 characters between slashes.
