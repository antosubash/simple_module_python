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

from simple_module_db import all_tenants, tenant_context

from background_tasks import tenant_context as task_tenant
from background_tasks.constants import OUTBOX_ERROR_MAX_LENGTH

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
def row_tenant(tenant_id: str | None) -> Generator[None]:
    """The tenant a delivery runs as: the publisher's, else the install default.

    Mirrors ``restore_tenant`` for ordinary tasks. With neither, the event was
    published as the platform (beat, a CLI, code inside ``all_tenants()``), and
    the handler runs in the platform scope the rest of the codebase uses for
    such work, ``all_tenants()`` — never in whatever tenant the dispatching
    task's own message carried. A platform handler that acts for one tenant
    enters ``tenant_context(id)`` itself.
    """
    resolved = tenant_id or task_tenant.default_tenant()
    if resolved:
        with tenant_context(resolved):
            yield
        return
    with all_tenants():
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
