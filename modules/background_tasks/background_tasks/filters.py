"""How the executions screen's filters become SQL.

Shared by the listing, the strip counts and the bulk retry. They live out here
rather than on the service because a bulk action scoped differently from the
table it sits above is how an operator ends up re-enqueueing rows they never
saw — one definition means they cannot drift apart.
"""

from __future__ import annotations

from simple_module_db import LIKE_ESCAPE_CHAR, like_contains_pattern
from sqlalchemy import ColumnElement, select

from background_tasks.constants import RETRYABLE_STATUSES, TaskStatus
from background_tasks.models import TaskExecution

Conditions = list[ColumnElement[bool]]


def execution_filters(
    *,
    status: TaskStatus | None = None,
    task_name: str | None = None,
    queue: str | None = None,
) -> Conditions:
    """The three axes the executions screen filters on."""
    conditions: Conditions = []
    if status is not None:
        conditions.append(TaskExecution.status == status)
    if task_name:
        conditions.append(
            TaskExecution.task_name.ilike(like_contains_pattern(task_name), escape=LIKE_ESCAPE_CHAR)
        )
    if queue:
        conditions.append(TaskExecution.queue == queue)
    return conditions


def bulk_retry_conditions(
    *,
    status: TaskStatus | None = None,
    task_name: str | None = None,
    queue: str | None = None,
) -> Conditions | None:
    """What the bulk sweep may touch, or ``None`` when it may touch nothing.

    Two rules on top of the screen's own filters.

    A status that is not retryable narrows the set to empty rather than
    widening it: pressing the button while looking at ``running`` queues
    nothing, because the button can never reach past what is on screen.

    A row that already has a child has already been re-queued, and sweeping it
    again would multiply the backlog on every press — two clicks on a wedged
    queue of 40 would enqueue 80 tasks. Excluding it makes the button
    idempotent in the way an operator expects. Retrying such a row
    *deliberately* is still possible through its own dialog, which says how
    many attempts it has had and makes the person decide.
    """
    wanted = RETRYABLE_STATUSES if status is None else RETRYABLE_STATUSES & {status}
    if not wanted:
        return None
    child = TaskExecution.__table__.alias("retry_child")
    already_retried = select(child.c.id).where(child.c.retried_from_id == TaskExecution.id).exists()
    return [
        TaskExecution.status.in_(sorted(wanted)),
        *execution_filters(task_name=task_name, queue=queue),
        ~already_retried,
    ]
