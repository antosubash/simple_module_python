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
(they hold the ASGI scope). Before send, events lose the `Authorization`,
`Cookie`, `Set-Cookie`, `X-CSRF-Token` and `X-Api-Key` headers, request cookies
and bodies, and the values of `token` and `code` query parameters (in the query
string and the URL).
