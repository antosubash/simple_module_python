# simple_module_background_tasks

Celery + Redis background-task module for [simple_module](https://github.com/antosubash/simple_module_python) apps. Provides a pre-configured Celery instance, a task registration hook, and an admin UI for monitoring + retrying failed/stuck tasks.

## Install

```bash
pip install simple_module_background_tasks
```

Requires a Redis broker — set `SM_CELERY_BROKER_URL` (default `redis://localhost:6379/0`).

## What it provides

- `register_background_tasks()` module hook — modules declare tasks here; the registry wires them into the Celery app at boot.
- Admin UI at `/background-tasks/admin` — list recent runs, retry failed, inspect tracebacks.
- Shared Celery app accessible via `from background_tasks import celery_app` (import name `background_tasks`, distribution name `simple_module_background_tasks`).

## Usage

Declare a task in a module:

```python
# modules/reports/reports/tasks.py
from background_tasks import celery_app   # type: ignore[import-not-found]


@celery_app.task(name="reports.generate")
def generate_report(report_id: int) -> None:
    ...
```

Register it:

```python
class ReportsModule(ModuleBase):
    meta = ModuleMeta(name="reports", depends_on=["background_tasks"])

    def register_background_tasks(self):
        from . import tasks  # noqa: F401 — side-effect: registers tasks
```

Enqueue from an endpoint:

```python
generate_report.delay(report_id=42)
```

Run a worker locally:

```bash
uv run celery -A background_tasks.celery_app worker --loglevel=info
```

## Worker log context

Every worker log line automatically carries the Celery task identifiers
that fired it. A `LogContextFilter` is attached when the Celery app is
built (`build_celery`) and the `task_prerun` / `task_postrun` signals
bind `task_id` + `task_name` into `contextvars` for the task's duration:

```jsonc
{"level": "INFO", "logger": "reports.tasks", "message": "ingest done",
 "task_id": "9c2a…", "task_name": "reports.generate"}
```

Use `bind_task_context(...)` to attach app-level identifiers (the
domain `job_id` that named a Celery task is the canonical example):

```python
from background_tasks import bind_task_context

@celery_app.task
def process_dataset(job_id: int) -> None:
    with bind_task_context(job_id=job_id):
        logger.info("starting ingest")   # now carries job_id too
```

Bindings nest cleanly and restore on exit. structlog users can mount the
same `contextvars` directly via `structlog.contextvars.merge_contextvars`.

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`
- `celery[redis]>=5.4`, `redis>=5`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
