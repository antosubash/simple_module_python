# Retained logging

`simple_module_hosting.log_sinks` lets a module keep log lines somewhere durable
without putting that work on the logging call. The `background_tasks` module
ships the database sink; any module can add another.

## The sink protocol

```python
class LogSink(Protocol):
    def emit_batch(self, records: Sequence[logging.LogRecord]) -> None: ...
```

`emit_batch` runs on a background thread, never in a request, and receives
records that have already been redacted. Raising is allowed: the batch is
counted in `QueueSinkHandler.failed_batches`, a warning is logged, and the
records are lost.

## Installing one

```python
from simple_module_hosting.log_sinks import install_sink, uninstall_sink

handler = install_sink(MySink(), level=logging.INFO)  # attaches to the root logger
...
uninstall_sink(handler)  # detaches and flushes
```

`QueueSinkHandler` is a `logging.handlers.QueueHandler` plus a listener thread:

| Behaviour | Detail |
|---|---|
| Batching | up to 200 records, or whatever arrived within 1 second |
| Bounded | 10,000 queued records; when full a record is dropped and counted in `handler.dropped`. Logging never blocks and cannot deadlock on a slow sink |
| Level | `level` is a threshold on the handler; the logger it is attached to must also pass the record (a root logger at `WARNING` never offers `INFO` lines) |
| Self-exclusion | records from `simple_module_hosting.log_sinks` and `sqlalchemy.*` are skipped, so a database sink cannot log about itself |
| Correlation | `record.correlation_id` is filled from the request context when unset |

Handler filters run on the emitting thread, where the request or task context
is bound. Add a filter to the handler (as `background_tasks` does for the task
id and the tenant) to capture context; the listener thread cannot see it.

## Redaction

`redact(text)` and `redact_record(record)` mask `Authorization`,
`Proxy-Authorization`, `Cookie` and `Set-Cookie` values, bearer tokens, and the
value of any `key=value` / `"key": "value"` whose key contains `password`,
`passwd`, `token`, `secret` or `api_key`. Extra attributes whose *name*
matches are replaced outright. `QueueSinkHandler` redacts a copy of the record
before queueing it, so the original, shared with every other handler, is never
changed. Redaction is pattern-based: it cannot recognise a secret that is
logged without a label.

## Database sink

See [Retained task and app logs](/modules/background_tasks#retained-task-and-app-logs)
for the table, settings, retention and the admin screens.
