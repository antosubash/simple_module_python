"""Single source of truth for background_tasks module string literals.

Anything that would otherwise become a magic string — table names, env-var
prefixes, permission codes, route segments, page identifiers, task-status
values — lives here so models, signals, services, endpoints, tests, and
the frontend all agree on one spelling.
"""

from __future__ import annotations

from enum import StrEnum

# ── Module identity ─────────────────────────────────────────────
MODULE_NAME = "background_tasks"
MODULE_DISPLAY_NAME = "BackgroundTasks"
TABLE_PREFIX = "background_tasks_"
TABLE_TASK_EXECUTION = f"{TABLE_PREFIX}task_execution"

# ── Module dependencies ─────────────────────────────────────────
_MODULE_USERS = "Users"

# ── Env / settings ──────────────────────────────────────────────
ENV_PREFIX = "SM_BG_TASKS_"

# ── Permissions ─────────────────────────────────────────────────
PERM_GROUP = "Background Tasks"
PERM_VIEW = "background_tasks.view"
PERM_MANAGE = "background_tasks.manage"

# ── Routes ──────────────────────────────────────────────────────
API_PREFIX = "/api/background_tasks"
VIEW_PREFIX = "/admin/background-tasks"
ADMIN_ROUTER_PREFIX = "/admin"

# ── Menu ────────────────────────────────────────────────────────
MENU_LABEL = "Background Tasks"
MENU_ICON = "activity"
MENU_ORDER = 120

# ── Page identifiers ────────────────────────────────────────────
# Kept as literals at the call site (see endpoints/views.py) so
# ``make doctor``'s SM003/SM004 static analysis can match pages to renders.


# ── Task statuses ───────────────────────────────────────────────
class TaskStatus(StrEnum):
    """Lifecycle state of a single task execution row."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    STUCK = "stuck"
    REVOKED = "revoked"
    RETRYING = "retrying"


RETRYABLE_STATUSES: frozenset[TaskStatus] = frozenset({TaskStatus.FAILED, TaskStatus.STUCK})
TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.STUCK, TaskStatus.REVOKED}
)

# ── Defaults ────────────────────────────────────────────────────
DEFAULT_QUEUE = "default"
DEFAULT_BROKER_URL = "redis://localhost:6379/0"
DEFAULT_RESULT_BACKEND = "redis://localhost:6379/1"
DEFAULT_STUCK_AFTER_SECONDS = 300
DEFAULT_STUCK_SWEEP_INTERVAL_SECONDS = 60
DEFAULT_PURGE_INTERVAL_SECONDS = 60 * 60 * 24
DEFAULT_RETENTION_DAYS = 14
DEFAULT_MAX_RETRIES = 3

# ── Internal task names ─────────────────────────────────────────
INTERNAL_TASK_SWEEP_STUCK = "background_tasks.sweep_stuck_tasks"
INTERNAL_TASK_PURGE_OLD = "background_tasks.purge_old_executions"
# Harmless round-trip task; only wired into CI smoke tests and local dev —
# not scheduled, not invoked by other modules.
DEMO_ECHO_TASK = "background_tasks.demo_echo"
