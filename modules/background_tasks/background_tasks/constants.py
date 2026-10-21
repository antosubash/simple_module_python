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
TABLE_OUTBOX = f"{TABLE_PREFIX}outbox"

# ── Module dependencies ─────────────────────────────────────────
# Sorted after Settings for its admin editor and reload path; registering
# settings itself no longer needs it (the framework owns the registry, #500).
_MODULE_SETTINGS = "Settings"

# ── Env / settings ──────────────────────────────────────────────
ENV_PREFIX = "SM_BG_TASKS_"

# The single Redis URL an operator sets. Seeds both the broker and the result
# backend: Celery namespaces result keys as ``celery-task-meta-*``, so sharing
# one database is safe and is what upstream's quickstart does. The per-field
# DB-backed overrides still allow splitting them.
ENV_REDIS_URL = "SM_REDIS_URL"

# ── Permissions ─────────────────────────────────────────────────
PERM_GROUP = "Background tasks"
PERM_VIEW = "background_tasks.view"
PERM_MANAGE = "background_tasks.manage"

# ── Routes ──────────────────────────────────────────────────────
API_PREFIX = "/api/background_tasks"
VIEW_PREFIX = "/admin/background-tasks"
ADMIN_ROUTER_PREFIX = "/admin"

# ── Menu ────────────────────────────────────────────────────────
MENU_LABEL = "Background tasks"
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

# How many executions one "Retry all failed" press may re-enqueue.
#
# The sweep publishes to the broker once per row and writes a row per publish,
# so an unbounded backlog turns one button into a multi-minute request holding
# a DB transaction open. Capping it makes the cost of a press knowable; the
# response says how many are left so the operator can press again.
RETRY_ALL_BATCH = 500

# ── Defaults ────────────────────────────────────────────────────
DEFAULT_QUEUE = "default"
DEFAULT_BROKER_URL = "redis://localhost:6379/0"
DEFAULT_RESULT_BACKEND = "redis://localhost:6379/1"
DEFAULT_STUCK_AFTER_SECONDS = 300
DEFAULT_STUCK_SWEEP_INTERVAL_SECONDS = 60
# ``heartbeat()`` writes at most this often per task, however often a task body
# calls it. Keep stuck thresholds well above it.
HEARTBEAT_MIN_INTERVAL_SECONDS = 30
# Task attribute giving one task its own stuck threshold, in seconds:
# ``@shared_task(name=..., stuck_after=4 * 3600)``. Celery copies extra
# decorator options onto the task class, so the sweep reads it off the registry.
TASK_STUCK_AFTER_ATTR = "stuck_after"
DEFAULT_PURGE_INTERVAL_SECONDS = 60 * 60 * 24
DEFAULT_RETENTION_DAYS = 14
DEFAULT_MAX_RETRIES = 3
# Redis pub/sub channel carrying the framework's cache invalidations. Namespaced
# so that two apps on one Redis *server* do not each act on the other's messages.
# The server, not the database: pub/sub ignores the logical DB index, so DBs 4 and
# 5 of one instance share this channel. Mostly that costs pointless reads, but it
# is not unconditionally harmless — an emptied cache is also what exposes
# ``UsersAuthProvider._version_still_current``'s fail-open branch, so rename it
# per app rather than relying on the DB number.
DEFAULT_INVALIDATION_CHANNEL = "simple_module.invalidation"

# ── Internal task names ─────────────────────────────────────────
INTERNAL_TASK_SWEEP_STUCK = "background_tasks.sweep_stuck_tasks"
INTERNAL_TASK_PURGE_OLD = "background_tasks.purge_old_executions"
INTERNAL_TASK_DISPATCH_OUTBOX = "background_tasks.dispatch_outbox"
INTERNAL_TASK_SWEEP_OUTBOX = "background_tasks.sweep_outbox"
BEAT_SWEEP_STUCK = "background-tasks-sweep-stuck"
BEAT_PURGE_OLD = "background-tasks-purge-old"
BEAT_SWEEP_OUTBOX = "background-tasks-sweep-outbox"
# Harmless round-trip task; only wired into CI smoke tests and local dev —
# not scheduled, not invoked by other modules.
DEMO_ECHO_TASK = "background_tasks.demo_echo"


# ── Durable event outbox (GH #459) ──────────────────────────────
class OutboxStatus(StrEnum):
    """Lifecycle of one (event, durable handler) delivery."""

    PENDING = "pending"
    RUNNING = "running"
    DELIVERED = "delivered"
    DEAD = "dead"


class OutboxScope(StrEnum):
    """The tenancy scope a durable event was published in, and is delivered in.

    ``tenant_id`` alone cannot tell the two ``None`` cases apart: a platform
    publish (inside ``all_tenants()``) may read across tenants, a publish with
    no tenant bound (a public route, an ordinary task without a tenant) may not.
    """

    TENANT = "tenant"
    PLATFORM = "platform"
    UNSCOPED = "unscoped"


DEFAULT_OUTBOX_MAX_ATTEMPTS = 8
DEFAULT_OUTBOX_SWEEP_INTERVAL_SECONDS = 30
# How long a claimed row stays ``running`` before another worker may reclaim it.
# Durable handlers are cut off ``outbox_lease_margin`` before it, so no run can
# outlive its claim and overlap the rerun a reclaim would start.
DEFAULT_OUTBOX_LEASE_SECONDS = 300
OUTBOX_LEASE_MARGIN_MIN_SECONDS = 5.0


def outbox_lease_margin(lease_seconds: float) -> float:
    """Room left inside a lease after the handler's timeout: 10 %, at least 5 s.

    Covers the delivered mark and commit that follow the handler.
    """
    return max(OUTBOX_LEASE_MARGIN_MIN_SECONDS, lease_seconds / 10)


def max_outbox_handler_timeout(lease_seconds: float) -> float:
    return lease_seconds - outbox_lease_margin(lease_seconds)


OUTBOX_BACKOFF_BASE_SECONDS = 10
OUTBOX_BACKOFF_CAP_SECONDS = 3600
# Default batch for ``claim``; the dispatcher itself claims one row at a time.
OUTBOX_CLAIM_BATCH = 100
# Rows one dispatch/sweep run delivers at most; the next sweep takes the rest.
OUTBOX_DISPATCH_LIMIT = 500
OUTBOX_ERROR_MAX_LENGTH = 4000
OUTBOX_KEY_MAX_LENGTH = 255

TENANT_ID_MAX_LENGTH = 50
# Filter value meaning "executions with no tenant" (beat / platform publishes).
PLATFORM_TENANT_FILTER = "__platform__"
