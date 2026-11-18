"""Database provider detection."""

from enum import StrEnum

from sqlalchemy.engine import make_url


class DatabaseProvider(StrEnum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


def detect_provider(database_url: str) -> DatabaseProvider:
    """Detect a supported provider, rejecting other dialects without leaking credentials."""
    dialect = make_url(database_url).get_backend_name()
    if dialect == "sqlite":
        return DatabaseProvider.SQLITE
    if dialect in {"postgresql", "postgres"}:
        return DatabaseProvider.POSTGRESQL
    raise ValueError(
        f"Unsupported database dialect {dialect!r}; supported dialects are sqlite and postgresql"
    )
