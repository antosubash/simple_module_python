"""Celery app and task bases that stamp and validate tenant authority on publish."""

from __future__ import annotations

from typing import Any

from celery import Celery, Task

from background_tasks.executions.tenant_context import stamp_owner, stamp_tenant


class TenantPublishMixin:
    """Stamp and validate authority on ``apply_async``, eager runs included.

    An eager ``apply_async`` runs the body in-process without ``send_task`` or
    the publish signal, so this is the only place its headers get the caller's
    tenant and owner (and a mismatching tenant header is refused).
    """

    def apply_async(
        self,
        args: Any = None,
        kwargs: Any = None,
        task_id: Any = None,
        producer: Any = None,
        link: Any = None,
        link_error: Any = None,
        shadow: Any = None,
        **options: Any,
    ) -> Any:
        # Explicit headers replace the task's default ones in Celery, so merge
        # them here or a task-level default header would be lost.
        defaults = self._get_exec_options().get("headers") or {}
        headers = {**defaults, **(options.get("headers") or {})}
        stamp_tenant(headers)
        if self.app.conf.task_always_eager:
            stamp_owner(headers)
        options["headers"] = headers
        return super().apply_async(
            args, kwargs, task_id, producer, link, link_error, shadow, **options
        )


class TenantTask(TenantPublishMixin, Task):
    """Default task base with tenant-aware publication."""


class TenantCelery(Celery):
    """Validate publish authority before Celery's exception-swallowing signals."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("task_cls", TenantTask)
        super().__init__(*args, **kwargs)

    def _task_from_fun(  # ty: ignore[invalid-method-override]
        self,
        fun: Any,
        name: Any = None,
        base: Any = None,
        bind: bool = False,
        **options: Any,
    ) -> Any:
        # ``@app.task(base=Custom)`` replaces ``task_cls``; keep the tenant
        # publish checks by composing them in front of the custom base.
        base = base or self.Task
        if not issubclass(base, TenantPublishMixin):
            label = base.__name__
            try:
                base = type(
                    label,
                    (TenantPublishMixin, base),
                    {"__module__": base.__module__, "__qualname__": base.__qualname__},
                )
            except TypeError as exc:
                raise TypeError(
                    f"Cannot compose tenant publish validation with task base {label}"
                ) from exc
        # Forward the rest untouched: the pydantic_* options only exist in Celery >= 5.5.
        return super()._task_from_fun(fun, name=name, base=base, bind=bind, **options)

    def send_task(self, name: str, *args: Any, **kwargs: Any) -> Any:
        headers = dict(kwargs.get("headers") or {})
        stamp_tenant(headers)
        kwargs["headers"] = headers
        return super().send_task(name, *args, **kwargs)
