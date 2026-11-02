"""Process-wide services the web app wires once at build time (#538, #539).

Kept out of ``create_app`` so the builder stays a list of phases. Both are also
configured by the Celery worker, which never runs ``create_app``.
"""

from __future__ import annotations

from typing import Any

from simple_module_hosting.leases import configure_process_leases
from simple_module_hosting.sentry import PROCESS_WEB, init_sentry


def configure_process_services(redis_url: str | None, *, engine: Any) -> None:
    """Start Sentry (a no-op without ``SM_SENTRY_DSN``) and pick the lease backend."""
    init_sentry(PROCESS_WEB)
    configure_process_leases(redis_url, engine=engine)
