"""Reading retained log lines for the admin screens (GH #537)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from simple_module_db import RequestSession
from simple_module_db.pagination import PageParams, paginate
from sqlalchemy import false, select
from sqlmodel import col

from background_tasks.constants import LOG_LEVEL_NAMES
from background_tasks.contracts.logs import LogItem, LogListResponse
from background_tasks.models import RetainedLog

_LEVEL_NAMES = {number: name for name, number in logging.getLevelNamesMapping().items()}


def level_number(name: str | None) -> int | None:
    """``"WARNING"`` → 30; ``None`` for an empty or unknown name (no filter)."""
    upper = (name or "").strip().upper()
    return logging.getLevelNamesMapping()[upper] if upper in LOG_LEVEL_NAMES else None


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@dataclass(frozen=True)
class LogScope:
    """Which tenants' lines the caller may read, as the outbox scope does."""

    everything: bool = False
    tenant_id: str | None = None

    def conditions(self) -> list[Any]:
        if self.everything:
            return []
        if self.tenant_id:
            return [RetainedLog.tenant_id == self.tenant_id]
        return [false()]


class LogService:
    def __init__(self, db: RequestSession, scope: LogScope) -> None:
        self.db = db
        self.scope = scope

    async def search(
        self,
        *,
        page: int,
        per_page: int,
        task_id: str | None = None,
        min_level: str | None = None,
        q: str | None = None,
        logger_name: str | None = None,
    ) -> LogListResponse:
        where = [*self.scope.conditions()]
        if task_id is not None:
            where.append(col(RetainedLog.task_id) == task_id)
        if (level := level_number(min_level)) is not None:
            where.append(col(RetainedLog.level) >= level)
        if q:
            where.append(col(RetainedLog.message).ilike(_like(q), escape="\\"))
        if logger_name:
            where.append(col(RetainedLog.logger).startswith(logger_name))
        found = await paginate(
            self.db,
            select(RetainedLog)
            .where(*where)
            .order_by(col(RetainedLog.ts).desc(), col(RetainedLog.id)),
            PageParams(page=page, per_page=per_page),
        )
        return LogListResponse(
            items=[
                LogItem.model_validate(
                    {**r.model_dump(), "level_name": _LEVEL_NAMES.get(r.level, str(r.level))}
                )
                for r in found.items
            ],
            total=found.total,
            page=found.page,
            per_page=found.per_page,
        )
