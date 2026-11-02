"""Restart-required worker engine settings."""

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings

_RESTART = {"requires_restart": True, "group": "Database"}


class WorkerDatabaseSettings(BaseSettings):
    """Inherited by BackgroundTasksSettings with its SM_BG_TASKS_ env prefix."""

    db_pool_size: int = Field(default=2, ge=1, json_schema_extra=_RESTART)
    db_max_overflow: int = Field(default=3, ge=0, json_schema_extra=_RESTART)
    db_recycle: int = Field(default=1800, ge=0, json_schema_extra=_RESTART)
    db_statement_timeout_ms: int | None = Field(default=None, ge=0, json_schema_extra=_RESTART)


def worker_database_options(host: Any, worker: WorkerDatabaseSettings) -> dict[str, int]:
    """Use host timeouts unless the worker has an explicit statement limit."""
    return {
        "pool_size": worker.db_pool_size,
        "max_overflow": worker.db_max_overflow,
        "pool_recycle": worker.db_recycle,
        "pool_timeout": host.db_pool_timeout,
        "connect_timeout": host.db_connect_timeout,
        "statement_timeout_ms": (
            host.db_statement_timeout_ms
            if worker.db_statement_timeout_ms is None
            else worker.db_statement_timeout_ms
        ),
        "idle_in_tx_timeout_ms": host.db_idle_in_tx_timeout_ms,
    }
