"""Audit sinks published through the ``simple_module.audit_sinks`` entry point.

A web process gets its audit sink from the module that owns it (``audit_log``
sets ``DatabaseState.audit_callback`` on startup). A process that never builds
the app — the Celery worker — has no ``DatabaseState`` to read, so it asks
the installed distributions instead: a module that stores audit records
declares::

    [project.entry-points."simple_module.audit_sinks"]
    audit_log = "audit_log.capture:audit_callback"

and the worker binds the result to its engine with
``EngineTenancy(audit_callback=...)``. Neither side imports the other (#498).
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from importlib.metadata import entry_points

from sqlalchemy.orm import Session

from simple_module_db.audit import AuditRecord

AUDIT_SINK_ENTRY_POINT_GROUP = "simple_module.audit_sinks"

AuditCallback = Callable[[Session, list[AuditRecord]], None]

logger = logging.getLogger(__name__)


@functools.cache
def discover_audit_callback() -> AuditCallback | None:
    """The installed audit sinks as one callback, or ``None`` if there are none.

    Cached: the installed distributions do not change while a process runs
    (``discover_audit_callback.cache_clear()`` in tests). A sink that fails to
    import is logged and skipped: auditing is lost for that sink, but the
    worker still boots and runs its tasks.
    """
    sinks: list[AuditCallback] = []
    found = entry_points(group=AUDIT_SINK_ENTRY_POINT_GROUP)
    for ep in sorted(found, key=lambda e: e.name):
        try:
            sinks.append(ep.load())
        except Exception:
            logger.exception("Could not load audit sink %r (%s)", ep.name, ep.value)
    if not sinks:
        return None
    if len(sinks) == 1:
        return sinks[0]

    def _fan_out(session: Session, records: list[AuditRecord]) -> None:
        for sink in sinks:
            sink(session, records)

    return _fan_out
