"""Small pieces of one outbox delivery: result counts, tenant scope, clock, errors."""

from __future__ import annotations

import logging
import time
import traceback
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from simple_module_db import all_tenants, no_tenant, tenant_context

from background_tasks import tenant_context as task_tenant
from background_tasks.constants import OUTBOX_ERROR_MAX_LENGTH, OutboxScope

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    delivered: int = 0
    retrying: int = 0
    dead: int = 0
    # Finished by someone else first (lease lost, row discarded): rolled back.
    fenced: int = 0
    reclaimed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "delivered": self.delivered,
            "retrying": self.retrying,
            "dead": self.dead,
            "fenced": self.fenced,
            "reclaimed": self.reclaimed,
        }


@contextmanager
def row_tenant(tenant_id: str | None, scope: str) -> Generator[None]:
    """The scope a delivery runs in: the one its publisher was in.

    Never whatever tenant the dispatching task's own message carried.

    - A tenant publish runs as that tenant.
    - A platform publish (made inside ``all_tenants()``) runs in
      ``all_tenants()``. A platform handler that acts for one tenant enters
      ``tenant_context(id)`` itself.
    - An unscoped publish (no tenant bound and not ``all_tenants()``: a public
      route, an ordinary task without a tenant) runs as the install's default
      tenant if it has one — as ``restore_tenant`` runs such a task — else
      with no tenant bound, so under strict isolation its handler fails closed
      exactly as its publisher would have. It must not inherit the platform
      scope: its payload came from code that could read no tenant's data.
    """
    if tenant_id:
        with tenant_context(tenant_id):
            yield
        return
    if scope == OutboxScope.PLATFORM:
        with all_tenants():
            yield
        return
    default = task_tenant.default_tenant()
    if default:
        with tenant_context(default):
            yield
        return
    with no_tenant():
        yield


def describe(exc: BaseException) -> str:
    """The exception line first (what the admin list shows), then the traceback's tail."""
    summary = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    room = max(0, OUTBOX_ERROR_MAX_LENGTH - len(summary) - 2)
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return f"{summary}\n\n{tb[-room:]}" if room else summary


class Clock:
    """The claim's database time plus the monotonic time elapsed since."""

    def __init__(self, claimed_at: datetime) -> None:
        self._base = claimed_at
        self._start = time.monotonic()

    def __call__(self) -> datetime:
        return self._base + timedelta(seconds=time.monotonic() - self._start)


async def rollback_quietly(session: Any) -> None:
    """Roll back after a failure; a connection a timeout cancelled mid-query
    may refuse, and the failure must still be recorded."""
    try:
        await session.rollback()
    except Exception:
        logger.warning("outbox.rollback_failed", exc_info=True)
