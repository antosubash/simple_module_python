"""Database provider detection."""

from enum import StrEnum


class DatabaseProvider(StrEnum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


def detect_provider(database_url: str) -> DatabaseProvider:
    """Detect the database provider from a connection URL."""
    url_lower = database_url.lower()
    if url_lower.startswith(("postgresql", "postgres")):
        return DatabaseProvider.POSTGRESQL
    return DatabaseProvider.SQLITE
