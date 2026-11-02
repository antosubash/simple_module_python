"""Driver-specific startup timeouts, shared by web and worker engines."""

from typing import Any

from sqlalchemy.engine import make_url

_ASYNCPG = "asyncpg"
_LIBPQ_DRIVERS = frozenset({"psycopg", "psycopg2"})
_POSTGRESQL = "postgresql"
_STATEMENT = "statement_timeout"
_IDLE = "idle_in_transaction_session_timeout"
_TIMEOUT = "timeout"
_SERVER_SETTINGS = "server_settings"
_CONNECT_TIMEOUT = "connect_timeout"
_OPTIONS = "options"


def connect_args(
    database_url: str,
    *,
    connect_timeout: int = 10,
    statement_timeout_ms: int = 0,
    idle_in_tx_timeout_ms: int = 0,
) -> dict[str, Any]:
    """Build startup arguments without opening a connection; zero omits a limit."""
    url = make_url(database_url)
    if url.get_backend_name() != _POSTGRESQL:
        return {}
    settings = {
        key: str(value)
        for key, value in (
            (_STATEMENT, statement_timeout_ms),
            (_IDLE, idle_in_tx_timeout_ms),
        )
        if value
    }
    driver = url.get_driver_name()
    args: dict[str, Any] = {}
    if driver == _ASYNCPG:
        if connect_timeout:
            args[_TIMEOUT] = connect_timeout
        if settings:
            args[_SERVER_SETTINGS] = settings
    elif driver in _LIBPQ_DRIVERS:
        if connect_timeout and _CONNECT_TIMEOUT not in url.query:  # URL wins
            args[_CONNECT_TIMEOUT] = connect_timeout
        if settings:
            # connect_args replace the URL's own ``options``; keep the operator's flags.
            own = url.query.get(_OPTIONS)
            own_flags = [own] if isinstance(own, str) else list(own or ())
            flags = [f"-c {key}={value}" for key, value in settings.items()]
            args[_OPTIONS] = " ".join([*own_flags, *flags])
    return args
