"""Map resolved host settings to the application engine (never bootstrap reads)."""

from typing import TypedDict

from simple_module_hosting.host_settings import HostSettings


class DatabaseOptions(TypedDict):
    """Engine keyword types for SQLAlchemy initialization."""

    pool_size: int
    max_overflow: int
    pool_pre_ping: bool
    pool_recycle: int
    pool_timeout: int
    connect_timeout: int
    statement_timeout_ms: int
    idle_in_tx_timeout_ms: int


def database_options(settings: HostSettings) -> DatabaseOptions:
    """Read all restart-required engine settings during app construction."""
    return {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_pre_ping": settings.db_pool_pre_ping,
        "pool_recycle": settings.db_pool_recycle,
        "pool_timeout": settings.db_pool_timeout,
        "connect_timeout": settings.db_connect_timeout,
        "statement_timeout_ms": settings.db_statement_timeout_ms,
        "idle_in_tx_timeout_ms": settings.db_idle_in_tx_timeout_ms,
    }
